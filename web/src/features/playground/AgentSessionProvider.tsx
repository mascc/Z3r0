import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { listAgents } from "../../shared/api/agents";
import {
  buildAgentStreamUrl,
  createAgentSession,
  deleteAgentSession,
  listAgentEvents,
  listAgentSessions,
} from "../../shared/api/agentSessions";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import { getStoredAccessToken } from "../../shared/auth/session";
import type {
  AgentInfo,
  AgentInputPart,
  AgentSessionSummary,
  AgentStreamCommand,
  AgentStreamEvent,
} from "../../shared/api/types";
import {
  chatReplay,
  disconnectChatTurn,
  finishChatTurn,
  initialChatState,
  streamReduce,
  type ChatState,
} from "./playgroundReducer";
import { bufferLiveEvent, waitOpen } from "./agentStream";

type ConnectionStatus = "idle" | "connecting" | "open" | "closed";

type SessionRuntime = {
  state: ChatState;
  status: ConnectionStatus;
  historyLoading: boolean;
  // user-overridden agent for this session; "" => fall back to server-side sticky
  agentCodeOverride: string;
};

const DEFAULT_RUNTIME: SessionRuntime = {
  state: initialChatState,
  status: "idle",
  historyLoading: false,
  agentCodeOverride: "",
};

const IDLE_CLOSE_MS = 5 * 60 * 1000;

type AgentSessionContextValue = {
  sessions: AgentSessionSummary[];
  sessionsLoading: boolean;
  refreshSessions: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  dropSessionRuntime: (sessionId: string) => void;
  ensureSessionRuntime: (sessionId: string) => void;
  getSessionRuntime: (sessionId: string | null) => Pick<SessionRuntime, "state" | "status" | "historyLoading">;

  activeSessionId: string | null;
  selectSession: (sessionId: string | null, options?: { navigateBlank?: boolean }) => void;

  chatState: ChatState;
  status: ConnectionStatus;
  historyLoading: boolean;

  agents: AgentInfo[];
  defaultAgentCode: string;
  activeAgentCode: string;
  setActiveAgentCode: (code: string) => void;
  getSessionAgentCode: (sessionId: string | null) => string;
  setSessionAgentCode: (sessionId: string, code: string) => void;

  send: (content: AgentInputPart[], sandboxContainerId?: number | null, sessionId?: string | null) => Promise<void>;
  interrupt: (sessionId?: string | null) => Promise<void>;
  cancelAll: (sessionId?: string | null) => Promise<void>;
};

const AgentSessionContext = createContext<AgentSessionContextValue | null>(null);

export function useAgentSessionContext(): AgentSessionContextValue {
  const value = useContext(AgentSessionContext);
  if (!value) throw new Error("useAgentSessionContext must be used inside AgentSessionProvider");
  return value;
}

export function AgentSessionProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [runtimes, setRuntimes] = useState<Map<string, SessionRuntime>>(() => new Map());

  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [defaultAgentCode, setDefaultAgentCode] = useState("");
  // pending pick for the next brand-new chat (when activeSessionId is still null)
  const [pendingAgentCode, setPendingAgentCode] = useState("");
  // sockets + timers live outside react state because their identity does not
  // drive rendering; one ws per session is kept alive across session switches
  const socketsRef = useRef<Map<string, WebSocket>>(new Map());
  const idleTimersRef = useRef<Map<string, number>>(new Map());
  const ensuredRef = useRef<Set<string>>(new Set());
  const historyReadyRef = useRef<Set<string>>(new Set());
  const loadingHistoryRef = useRef<Set<string>>(new Set());
  const pendingLiveEventsRef = useRef<Map<string, AgentStreamEvent[]>>(new Map());
  const pendingSendRef = useRef<{
    sessionId: string;
    content: AgentInputPart[];
    sandboxContainerId: number | null;
    agentCode: string;
  } | null>(null);
  const manualBlankSessionRef = useRef(false);

  // ---------------------------------------------------------------- helpers
  const initRuntime = useCallback((sessionId: string) => {
    setRuntimes((prev) => {
      if (prev.has(sessionId)) return prev;
      const next = new Map(prev);
      next.set(sessionId, DEFAULT_RUNTIME);
      return next;
    });
  }, []);

  const updateRuntime = useCallback((sessionId: string, fn: (r: SessionRuntime) => SessionRuntime) => {
    setRuntimes((prev) => {
      const current = prev.get(sessionId);
      if (!current) return prev;
      const next = new Map(prev);
      next.set(sessionId, fn(current));
      return next;
    });
  }, []);

  const dropRuntime = useCallback((sessionId: string) => {
    setRuntimes((prev) => {
      if (!prev.has(sessionId)) return prev;
      const next = new Map(prev);
      next.delete(sessionId);
      return next;
    });
    ensuredRef.current.delete(sessionId);
    historyReadyRef.current.delete(sessionId);
    loadingHistoryRef.current.delete(sessionId);
    pendingLiveEventsRef.current.delete(sessionId);
  }, []);

  // ------------------------------------------------------------- agents
  useEffect(() => {
    listAgents()
      .then((response) => {
        setAgents(response.data?.items ?? []);
        setDefaultAgentCode(response.data?.default_code ?? "");
      })
      .catch(showApiError);
  }, []);

  // ------------------------------------------------------------- sessions
  const refreshSessions = useCallback(async (silent = false) => {
    if (!silent) setSessionsLoading(true);
    try {
      const response = await listAgentSessions();
      const items = response.data?.items ?? [];
      setSessions(items);
      for (const session of items) {
        if (session.is_running) initRuntime(session.session_id);
      }
    } catch (error) {
      if (!silent) showApiError(error);
    } finally {
      if (!silent) setSessionsLoading(false);
    }
  }, [initRuntime]);

  const refreshSessionsRef = useRef(refreshSessions);
  refreshSessionsRef.current = refreshSessions;

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  // ------------------------------------------------------------ ws + idle
  const clearIdleTimer = useCallback((sessionId: string) => {
    const timer = idleTimersRef.current.get(sessionId);
    if (timer != null) {
      window.clearTimeout(timer);
      idleTimersRef.current.delete(sessionId);
    }
  }, []);

  const closeSocket = useCallback((sessionId: string) => {
    clearIdleTimer(sessionId);
    const socket = socketsRef.current.get(sessionId);
    if (!socket) return;
    socketsRef.current.delete(sessionId);
    socket.close();
    updateRuntime(sessionId, (r) => ({
      ...r,
      status: "closed",
      state: disconnectChatTurn(r.state),
    }));
  }, [clearIdleTimer, updateRuntime]);

  const dropSessionRuntime = useCallback((sessionId: string) => {
    closeSocket(sessionId);
    dropRuntime(sessionId);
  }, [closeSocket, dropRuntime]);

  const markActivity = useCallback((sessionId: string) => {
    clearIdleTimer(sessionId);
    if (!socketsRef.current.has(sessionId)) return;
    const timer = window.setTimeout(() => closeSocket(sessionId), IDLE_CLOSE_MS);
    idleTimersRef.current.set(sessionId, timer);
  }, [clearIdleTimer, closeSocket]);

  const applyStreamEvent = useCallback((sessionId: string, parsed: AgentStreamEvent) => {
    if (parsed.type === "done") {
      updateRuntime(sessionId, (r) => ({
        ...r,
        state: finishChatTurn(r.state),
      }));
      return;
    }
    if (parsed.type === "run_state" && !parsed.running) {
      updateRuntime(sessionId, (r) => ({
        ...r,
        state: streamReduce(r.state, parsed),
      }));
      pendingLiveEventsRef.current.delete(sessionId);
      reloadHistoryRef.current(sessionId, true);
      void refreshSessionsRef.current(true);
      return;
    }
    // user_message echo signals the backend has materialized the session
    if (parsed.type === "user_message") {
      void refreshSessionsRef.current(true);
    }
    updateRuntime(sessionId, (r) => ({
      ...r,
      state: streamReduce(r.state, parsed),
    }));
  }, [updateRuntime]);

  const connectFor = useCallback((sessionId: string): WebSocket => {
    const existing = socketsRef.current.get(sessionId);
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return existing;
    }

    const token = getStoredAccessToken();
    if (!token) throw new Error("missing access token");

    const socket = new WebSocket(buildAgentStreamUrl(sessionId, token));
    socketsRef.current.set(sessionId, socket);
    initRuntime(sessionId);
    updateRuntime(sessionId, (r) => ({ ...r, status: "connecting" }));

    socket.addEventListener("open", () => {
      if (socketsRef.current.get(sessionId) !== socket) return;
      updateRuntime(sessionId, (r) => ({ ...r, status: "open" }));
      markActivity(sessionId);
      if (!ensuredRef.current.has(sessionId) && !loadingHistoryRef.current.has(sessionId)) {
        reloadHistoryRef.current(sessionId);
      }
    });

    const onTerminate = (event: CloseEvent | Event) => {
      if (socketsRef.current.get(sessionId) !== socket) return;
      socketsRef.current.delete(sessionId);
      clearIdleTimer(sessionId);
      socket.removeEventListener("close", onTerminate);
      socket.removeEventListener("error", onTerminate);
      updateRuntime(sessionId, (r) => ({
        ...r,
        status: "closed",
        state: r.state.streaming
          ? finishChatTurn(streamReduce(r.state, {
              type: "error",
              created_at: new Date().toISOString(),
              agent_name: "",
              nested_for: "",
              nested_call_id: "",
              message: websocketCloseMessage(event),
              code: "connection_closed",
            }))
          : disconnectChatTurn(r.state),
      }));
    };
    socket.addEventListener("close", onTerminate);
    socket.addEventListener("error", onTerminate);

    socket.addEventListener("message", (event) => {
      if (socketsRef.current.get(sessionId) !== socket) return;
      markActivity(sessionId);
      try {
        const parsed = JSON.parse(event.data) as AgentStreamEvent;
        if (!historyReadyRef.current.has(sessionId) || loadingHistoryRef.current.has(sessionId)) {
          bufferLiveEvent(sessionId, parsed, pendingLiveEventsRef.current);
          return;
        }
        applyStreamEvent(sessionId, parsed);
      } catch {
        // backend only emits json frames; swallow malformed payloads defensively
      }
    });
    return socket;
  }, [applyStreamEvent, clearIdleTimer, initRuntime, markActivity, updateRuntime]);

  const sendCommand = useCallback(async (sessionId: string, command: AgentStreamCommand) => {
    const socket = connectFor(sessionId);
    if (socket.readyState !== WebSocket.OPEN) {
      await waitOpen(socket);
    }
    markActivity(sessionId);
    socket.send(JSON.stringify(command));
  }, [connectFor, markActivity]);

  // ---------------------------------------------------------- history load
  const loadHistory = useCallback((sessionId: string, markEnsured: boolean, forceReplace = false) => {
    if (!forceReplace && loadingHistoryRef.current.has(sessionId)) {
      return;
    }
    initRuntime(sessionId);
    loadingHistoryRef.current.add(sessionId);
    if (forceReplace) {
      historyReadyRef.current.delete(sessionId);
      pendingLiveEventsRef.current.delete(sessionId);
    }
    updateRuntime(sessionId, (r) => ({ ...r, historyLoading: true }));

    listAgentEvents(sessionId)
      .then((response) => {
        const events = response.data?.items ?? [];
        const buffered = pendingLiveEventsRef.current.get(sessionId) ?? [];
        const bufferedIdle = buffered.some((event) => event.type === "run_state" && !event.running);
        pendingLiveEventsRef.current.delete(sessionId);
        if (markEnsured) ensuredRef.current.add(sessionId);
        historyReadyRef.current.add(sessionId);
        loadingHistoryRef.current.delete(sessionId);
        updateRuntime(sessionId, (r) => ({
          ...r,
          state: buffered.reduce(streamReduce, chatReplay(events)),
          historyLoading: false,
        }));
        connectForRef.current(sessionId);
        if (bufferedIdle && !forceReplace) {
          reloadHistoryRef.current(sessionId, true);
          void refreshSessionsRef.current(true);
        }
      })
      .catch((error) => {
        ensuredRef.current.delete(sessionId);
        historyReadyRef.current.delete(sessionId);
        loadingHistoryRef.current.delete(sessionId);
        pendingLiveEventsRef.current.delete(sessionId);
        showApiError(error);
        updateRuntime(sessionId, (r) => ({ ...r, historyLoading: false }));
      });
  }, [initRuntime, updateRuntime]);

  const ensureHistoryLoaded = useCallback((sessionId: string) => {
    if (ensuredRef.current.has(sessionId)) return;
    loadHistory(sessionId, true);
  }, [loadHistory]);

  const ensureSessionRuntime = useCallback((sessionId: string) => {
    if (ensuredRef.current.has(sessionId)) {
      connectFor(sessionId);
      return;
    }
    ensureHistoryLoaded(sessionId);
  }, [connectFor, ensureHistoryLoaded]);

  const reloadHistory = useCallback((sessionId: string, forceReplace = false) => {
    loadHistory(sessionId, false, forceReplace);
  }, [loadHistory]);

  const reloadHistoryRef = useRef(reloadHistory);
  reloadHistoryRef.current = reloadHistory;
  const connectForRef = useRef<(sessionId: string) => WebSocket>(() => {
    throw new Error("agent stream connector is not ready");
  });
  connectForRef.current = connectFor;

  // ----------------------------------------------------------- selection
  const selectSession = useCallback((sessionId: string | null, options: { navigateBlank?: boolean } = {}) => {
    if (!sessionId || pendingSendRef.current?.sessionId !== sessionId) {
      pendingSendRef.current = null;
    }
    manualBlankSessionRef.current = sessionId === null && options.navigateBlank !== false;
    setActiveSessionId(sessionId);
  }, []);

  useEffect(() => {
    if (!activeSessionId) return;
    if (ensuredRef.current.has(activeSessionId)) {
      connectFor(activeSessionId);
      return;
    }
    ensureHistoryLoaded(activeSessionId);
  }, [activeSessionId, connectFor, ensureHistoryLoaded]);

  useEffect(() => {
    const runningSessions = sessions.filter((session) => session.is_running);
    if (!runningSessions.length) return;

    if (!activeSessionId && !manualBlankSessionRef.current) {
      const [first] = runningSessions;
      if (first) setActiveSessionId(first.session_id);
    }

    for (const session of runningSessions) {
      if (ensuredRef.current.has(session.session_id)) {
        connectFor(session.session_id);
        continue;
      }
      ensureHistoryLoaded(session.session_id);
    }
  }, [activeSessionId, connectFor, ensureHistoryLoaded, sessions]);

  // ------------------------------------------------------------- agentCode
  const sessionAgentCode = useCallback(
    (sessionId: string | null): string => {
      if (!sessionId) return "";
      return sessions.find((session) => session.session_id === sessionId)?.agent_code ?? "";
    },
    [sessions],
  );

  const activeAgentCode = useMemo(() => {
    if (!activeSessionId) {
      return pendingAgentCode || defaultAgentCode;
    }
    const runtime = runtimes.get(activeSessionId);
    if (runtime?.agentCodeOverride) return runtime.agentCodeOverride;
    return sessionAgentCode(activeSessionId) || defaultAgentCode;
  }, [activeSessionId, defaultAgentCode, pendingAgentCode, runtimes, sessionAgentCode]);

  const setActiveAgentCode = useCallback((code: string) => {
    if (!agents.some((agent) => agent.code === code)) return;
    if (!activeSessionId) {
      setPendingAgentCode(code);
      return;
    }
    initRuntime(activeSessionId);
    updateRuntime(activeSessionId, (r) => ({ ...r, agentCodeOverride: code }));
  }, [activeSessionId, agents, initRuntime, updateRuntime]);

  const getSessionAgentCode = useCallback((sessionId: string | null) => {
    if (!sessionId) return pendingAgentCode || defaultAgentCode;
    const runtime = runtimes.get(sessionId);
    if (runtime?.agentCodeOverride) return runtime.agentCodeOverride;
    return sessionAgentCode(sessionId) || defaultAgentCode;
  }, [defaultAgentCode, pendingAgentCode, runtimes, sessionAgentCode]);

  const setSessionAgentCode = useCallback((sessionId: string, code: string) => {
    if (!agents.some((agent) => agent.code === code)) return;
    initRuntime(sessionId);
    updateRuntime(sessionId, (r) => ({ ...r, agentCodeOverride: code }));
  }, [agents, initRuntime, updateRuntime]);

  // ------------------------------------------------------------- commands
  // drain a queued send once the lazy-created session has loaded its history
  useEffect(() => {
    const queued = pendingSendRef.current;
    if (!queued || queued.sessionId !== activeSessionId) return;
    const runtime = runtimes.get(activeSessionId);
    if (!runtime || runtime.historyLoading) return;
    pendingSendRef.current = null;
    setPendingAgentCode("");
    sendCommand(activeSessionId, {
      action: "send",
      content: queued.content,
      sandbox_container_id: queued.sandboxContainerId,
      agent_code: queued.agentCode || null,
    }).catch(showApiError);
  }, [activeSessionId, runtimes, sendCommand, updateRuntime]);

  const send = useCallback(async (content: AgentInputPart[], sandboxContainerId: number | null = null, sessionId: string | null = activeSessionId) => {
    const agentCode = getSessionAgentCode(sessionId);
    if (sessionId) {
      await sendCommand(sessionId, {
        action: "send",
        content,
        sandbox_container_id: sandboxContainerId,
        agent_code: agentCode || null,
      });
      return;
    }
    // lazy-create path: defer the actual send until activeSessionId + history settle
    try {
      const response = await createAgentSession();
      const id = response.data?.session_id ?? null;
      if (!id) return;
      initRuntime(id);
      pendingSendRef.current = { sessionId: id, content, sandboxContainerId, agentCode };
      manualBlankSessionRef.current = false;
      setActiveSessionId(id);
    } catch (error) {
      showApiError(error);
    }
  }, [activeSessionId, getSessionAgentCode, initRuntime, sendCommand]);

  const interrupt = useCallback(async (sessionId: string | null = activeSessionId) => {
    const targetSessionId = sessionId ?? activeSessionId;
    if (!targetSessionId) return;
    try {
      await sendCommand(targetSessionId, { action: "interrupt" });
    } catch (error) {
      showApiError(error);
    }
  }, [activeSessionId, sendCommand]);

  const cancelAll = useCallback(async (sessionId: string | null = activeSessionId) => {
    const targetSessionId = sessionId ?? activeSessionId;
    if (!targetSessionId) return;
    try {
      await sendCommand(targetSessionId, { action: "cancel_all" });
    } catch (error) {
      showApiError(error);
    }
  }, [activeSessionId, sendCommand]);

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      const response = await deleteAgentSession(sessionId);
      showApiSuccess(response);
      closeSocket(sessionId);
      dropRuntime(sessionId);
      if (activeSessionId === sessionId) selectSession(null);
      await refreshSessions();
    } catch (error) {
      showApiError(error);
    }
  }, [activeSessionId, closeSocket, dropRuntime, refreshSessions, selectSession]);

  // -------------------------------------------------------------- unmount
  useEffect(() => {
    return () => {
      for (const socket of socketsRef.current.values()) socket.close();
      for (const timer of idleTimersRef.current.values()) window.clearTimeout(timer);
      socketsRef.current.clear();
      idleTimersRef.current.clear();
      ensuredRef.current.clear();
      historyReadyRef.current.clear();
      loadingHistoryRef.current.clear();
      pendingLiveEventsRef.current.clear();
    };
  }, []);

  // -------------------------------------------------------------- derived
  const activeRuntime = activeSessionId ? runtimes.get(activeSessionId) ?? DEFAULT_RUNTIME : DEFAULT_RUNTIME;
  const getSessionRuntime = useCallback((sessionId: string | null) => {
    const runtime = sessionId ? runtimes.get(sessionId) ?? DEFAULT_RUNTIME : DEFAULT_RUNTIME;
    return {
      state: runtime.state,
      status: runtime.status,
      historyLoading: runtime.historyLoading,
    };
  }, [runtimes]);

  const value = useMemo<AgentSessionContextValue>(() => ({
    sessions, sessionsLoading, refreshSessions, deleteSession,
    dropSessionRuntime, ensureSessionRuntime, getSessionRuntime,
    activeSessionId, selectSession,
    chatState: activeRuntime.state,
    status: activeRuntime.status,
    historyLoading: activeRuntime.historyLoading,
    agents, defaultAgentCode, activeAgentCode, setActiveAgentCode,
    getSessionAgentCode, setSessionAgentCode,
    send, interrupt, cancelAll,
  }), [
    sessions, sessionsLoading, refreshSessions, deleteSession,
    dropSessionRuntime, ensureSessionRuntime, getSessionRuntime,
    activeSessionId, selectSession,
    activeRuntime,
    agents, defaultAgentCode, activeAgentCode, setActiveAgentCode,
    getSessionAgentCode, setSessionAgentCode,
    send, interrupt, cancelAll,
  ]);

  return <AgentSessionContext.Provider value={value}>{children}</AgentSessionContext.Provider>;
}

function websocketCloseMessage(event: CloseEvent | Event): string {
  if (event instanceof CloseEvent) {
    if (event.reason) return `Agent stream connection closed: ${event.reason}`;
    if (event.code === 1009) return "Agent stream connection closed because the image payload is too large";
    if (event.code !== 1000 && event.code !== 1005) {
      return `Agent stream connection closed unexpectedly (code ${event.code})`;
    }
  }
  return "Agent stream connection closed before the model returned output";
}
