import { Button, Spin } from "@douyinfe/semi-ui";
import { Activity, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAdminAgentSession, useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { createAgentSession } from "../../shared/api/agentSessions";
import { showApiError } from "../../shared/api/feedback";
import { ChatStream } from "./ChatStream";
import { Composer } from "./Composer";

type PlaygroundLocationState = { sessionId?: string };

type PendingSend = { sessionId: string; text: string };
type RefreshAfterTurn = { sessionId: string; minNodeCount: number; sawStreaming: boolean };

export function PlaygroundPage() {
  const [pendingSend, setPendingSend] = useState<PendingSend | null>(null);
  const [refreshAfterTurn, setRefreshAfterTurn] = useState<RefreshAfterTurn | null>(null);
  const setHeaderActions = useAdminHeaderActions();
  const { activeAgentSessionId, setActiveAgentSessionId, refreshAgentSessions, agentSession } = useAdminAgentSession();
  const location = useLocation();
  const navigate = useNavigate();

  // consume sessionId from navigate state (e.g. Project "Go") then clear so
  // back-navigation does not retrigger the jump.
  useEffect(() => {
    const incoming = (location.state as PlaygroundLocationState | null)?.sessionId;
    if (incoming) {
      setActiveAgentSessionId(incoming);
      navigate(location.pathname, { replace: true });
    }
  }, [location.pathname, location.state, navigate, setActiveAgentSessionId]);

  const { state, status, historyLoading, loadedSessionId, send, interrupt } = agentSession;
  const composerDisabled = Boolean(activeAgentSessionId && loadedSessionId !== activeAgentSessionId);

  // titles + message counts may change after a turn completes; wait until
  // the sent turn actually starts so lazy-created chat sessions are materialized.
  useEffect(() => {
    if (!refreshAfterTurn || activeAgentSessionId !== refreshAfterTurn.sessionId) return;

    if (state.streaming) {
      if (!refreshAfterTurn.sawStreaming) {
        setRefreshAfterTurn({ ...refreshAfterTurn, sawStreaming: true });
      }
      return;
    }

    if (refreshAfterTurn.sawStreaming && state.nodes.length > refreshAfterTurn.minNodeCount) {
      setRefreshAfterTurn(null);
      void refreshAgentSessions();
    }
  }, [activeAgentSessionId, refreshAfterTurn, refreshAgentSessions, state.nodes.length, state.streaming]);

  const handleCreate = useCallback(async () => {
    try {
      const response = await createAgentSession();
      const id = response.data?.session_id;
      if (id) {
        setActiveAgentSessionId(id);
      }
    } catch (error) {
      showApiError(error);
    }
  }, [setActiveAgentSessionId]);

  const handleSend = useCallback(async (text: string) => {
    if (activeAgentSessionId) {
      setRefreshAfterTurn({ sessionId: activeAgentSessionId, minNodeCount: state.nodes.length, sawStreaming: false });
      try {
        await send(text);
      } catch (error) {
        setRefreshAfterTurn(null);
        showApiError(error);
      }
      return;
    }
    // Lazily allocate a session, queue the text, drain after the hook binds.
    try {
      const response = await createAgentSession();
      const id = response.data?.session_id;
      if (!id) return;
      setPendingSend({ sessionId: id, text });
      setRefreshAfterTurn({ sessionId: id, minNodeCount: 0, sawStreaming: false });
      setActiveAgentSessionId(id);
    } catch (error) {
      showApiError(error);
    }
  }, [activeAgentSessionId, send, setActiveAgentSessionId, state.nodes.length]);

  useEffect(() => {
    setHeaderActions(
      <>
        <Button icon={<Plus size={16} />} theme="solid" type="primary" onClick={() => void handleCreate()}>
          New chat
        </Button>
        <span className={`stream-status stream-status-${status}`}>
          <Activity size={14} />
          <span>{statusLabel(status)}</span>
        </span>
      </>,
    );
    return () => setHeaderActions(null);
  }, [handleCreate, setHeaderActions, status]);

  useEffect(() => {
    if (!pendingSend) return;
    if (pendingSend.sessionId !== loadedSessionId) return;
    const { sessionId, text } = pendingSend;
    setPendingSend(null);
    void send(text).catch((error) => {
      setRefreshAfterTurn((pending) => (pending?.sessionId === sessionId ? null : pending));
      showApiError(error);
    });
  }, [pendingSend, loadedSessionId, send]);

  return (
    <div className="playground-shell">
      <div className="playground-main">
        <div className="playground-canvas">
          <Spin spinning={historyLoading} wrapperClassName="playground-spin">
            <ChatStream nodes={state.nodes} streaming={state.streaming} />
          </Spin>
        </div>
        <div className="playground-composer">
          <Composer
            streaming={state.streaming}
            disabled={composerDisabled}
            onSend={(text) => void handleSend(text)}
            onInterrupt={() => void interrupt()}
          />
        </div>
      </div>
    </div>
  );
}

function statusLabel(status: string) {
  switch (status) {
    case "open":
      return "Live";
    case "connecting":
      return "Connecting";
    case "closed":
      return "Disconnected";
    default:
      return "Idle";
  }
}
