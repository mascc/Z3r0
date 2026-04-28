import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { buildAgentStreamUrl, listAgentEvents } from "../../shared/api/agentSessions";
import { showApiError } from "../../shared/api/feedback";
import { getStoredAccessToken } from "../../shared/auth/session";
import type { AgentContentEvent, AgentStreamCommand, AgentStreamEvent } from "../../shared/api/types";
import {
  chatReduce,
  chatReplay,
  finishChatTurn,
  initialChatState,
  type ChatState,
} from "./playgroundReducer";

type ConnectionStatus = "idle" | "connecting" | "open" | "closed";

type ReducerAction =
  | { kind: "event"; event: AgentContentEvent }
  | { kind: "finish" }
  | { kind: "set"; state: ChatState };

const IDLE_CLOSE_MS = 5 * 60 * 1000;
const CONNECT_TIMEOUT_MS = 15 * 1000;

const reducer = (state: ChatState, action: ReducerAction): ChatState => {
  if (action.kind === "event") return chatReduce(state, action.event);
  if (action.kind === "finish") return finishChatTurn(state);
  return action.state;
};

function isControlEvent(event: AgentStreamEvent): event is Extract<AgentStreamEvent, { type: "done" }> {
  return event.type === "done";
}

export function useAgentSession(sessionId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialChatState);
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loadedSessionId, setLoadedSessionId] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const streamingRef = useRef(false);
  streamingRef.current = state.streaming;

  const finalizeStreaming = useCallback(() => {
    if (streamingRef.current) {
      dispatch({ kind: "finish" });
    }
  }, []);

  const clearIdleTimer = useCallback(() => {
    if (idleTimerRef.current !== null) {
      window.clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
  }, []);

  const closeSocket = useCallback(() => {
    clearIdleTimer();
    const socket = socketRef.current;
    if (!socket) return;
    socketRef.current = null;
    socket.close();
    setStatus("closed");
    finalizeStreaming();
  }, [clearIdleTimer, finalizeStreaming]);

  const markActivity = useCallback(() => {
    clearIdleTimer();
    if (!socketRef.current) return;
    idleTimerRef.current = window.setTimeout(() => {
      closeSocket();
    }, IDLE_CLOSE_MS);
  }, [clearIdleTimer, closeSocket]);

  useEffect(() => {
    closeSocket();
    setStatus("idle");
    setLoadedSessionId(null);
    dispatch({ kind: "set", state: initialChatState });

    if (!sessionId) return;

    let cancelled = false;
    setHistoryLoading(true);
    listAgentEvents(sessionId)
      .then((response) => {
        if (cancelled) return;
        const events = (response.data?.items ?? []) as AgentContentEvent[];
        dispatch({ kind: "set", state: chatReplay(events) });
      })
      .catch(showApiError)
      .finally(() => {
        if (!cancelled) {
          setHistoryLoading(false);
          setLoadedSessionId(sessionId);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [closeSocket, sessionId]);

  const connect = useCallback(() => {
    if (!sessionId) throw new Error("no active agent session");
    const token = getStoredAccessToken();
    if (!token) throw new Error("missing access token");

    const existing = socketRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return existing;
    }

    const socket = new WebSocket(buildAgentStreamUrl(sessionId, token));
    socketRef.current = socket;
    setStatus("connecting");

    socket.addEventListener("open", () => {
      if (socketRef.current !== socket) return;
      setStatus("open");
      markActivity();
    });
    socket.addEventListener("close", () => {
      if (socketRef.current !== socket) return;
      socketRef.current = null;
      clearIdleTimer();
      setStatus("closed");
      finalizeStreaming();
    });
    socket.addEventListener("error", () => {
      if (socketRef.current !== socket) return;
      socketRef.current = null;
      clearIdleTimer();
      setStatus("closed");
      finalizeStreaming();
    });
    socket.addEventListener("message", (event) => {
      if (socketRef.current !== socket) return;
      markActivity();
      try {
        const parsed = JSON.parse(event.data) as AgentStreamEvent;
        if (isControlEvent(parsed)) {
          dispatch({ kind: "finish" });
          return;
        }
        dispatch({ kind: "event", event: parsed });
      } catch {
        // backend only emits json frames; swallow malformed payloads defensively
      }
    });

    return socket;
  }, [clearIdleTimer, finalizeStreaming, markActivity, sessionId]);

  const sendCommand = useCallback(
    async (command: AgentStreamCommand) => {
      const socket = connect();
      if (socket.readyState !== WebSocket.OPEN) {
        await new Promise<void>((resolve, reject) => {
          const cleanup = () => {
            window.clearTimeout(timer);
            socket.removeEventListener("open", onOpen);
            socket.removeEventListener("error", onError);
            socket.removeEventListener("close", onClose);
          };
          const onOpen = () => {
            cleanup();
            resolve();
          };
          const onError = () => {
            cleanup();
            reject(new Error("websocket connection failed"));
          };
          const onClose = () => {
            cleanup();
            reject(new Error("websocket connection closed"));
          };
          const timer = window.setTimeout(() => {
            cleanup();
            reject(new Error("websocket connection timed out"));
          }, CONNECT_TIMEOUT_MS);
          socket.addEventListener("open", onOpen);
          socket.addEventListener("error", onError);
          socket.addEventListener("close", onClose);
        });
      }
      markActivity();
      socket.send(JSON.stringify(command));
    },
    [connect, markActivity],
  );

  const send = useCallback((text: string) => sendCommand({ action: "send", text }), [sendCommand]);
  const interrupt = useCallback(() => sendCommand({ action: "interrupt" }), [sendCommand]);

  useEffect(() => {
    return closeSocket;
  }, [closeSocket]);

  return {
    state,
    status,
    historyLoading,
    loadedSessionId,
    send,
    interrupt,
  };
}
