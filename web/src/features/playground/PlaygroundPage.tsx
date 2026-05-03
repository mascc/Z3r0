import { Button, Spin } from "@douyinfe/semi-ui";
import { Activity, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { showApiError } from "../../shared/api/feedback";
import { queryAvailableSandboxContainers } from "../../shared/api/sandboxContainers";
import type { SandboxContainer } from "../../shared/api/types";
import { useAgentSessionContext } from "./AgentSessionProvider";
import { ChatStream } from "./ChatStream";
import { Composer } from "./Composer";
import { SandboxSelector } from "./SandboxSelector";

type PlaygroundLocationState = { sessionId?: string };

const STATUS_LABEL: Record<string, string> = {
  open: "Live",
  connecting: "Connecting",
  closed: "Disconnected",
  idle: "Idle",
};

const SANDBOX_REFRESH_MS = 5000;

export function PlaygroundPage() {
  const setHeaderActions = useAdminHeaderActions();
  const {
    activeSessionId, selectSession,
    chatState, status, historyLoading,
    agents, activeAgentCode, setActiveAgentCode,
    send, interrupt,
  } = useAgentSessionContext();
  const location = useLocation();
  const navigate = useNavigate();
  const [sandboxContainers, setSandboxContainers] = useState<SandboxContainer[]>([]);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [sandboxContainerId, setSandboxContainerId] = useState<number | null>(null);
  const [followLatest, setFollowLatest] = useState(true);
  const scrollToLatestRef = useRef<(() => void) | null>(null);

  const loadSandboxes = useCallback(async () => {
    setSandboxLoading(true);
    try {
      const response = await queryAvailableSandboxContainers({ page: 1, size: 100, keyword: "" });
      setSandboxContainers(response.data?.items ?? []);
    } catch (error) {
      showApiError(error);
    } finally {
      setSandboxLoading(false);
    }
  }, []);

  // consume sessionId from navigate state (e.g. project "Go") then clear so
  // back-navigation does not retrigger the jump
  useEffect(() => {
    const incoming = (location.state as PlaygroundLocationState | null)?.sessionId;
    if (incoming) {
      selectSession(incoming);
      navigate(location.pathname, { replace: true });
    }
  }, [location.pathname, location.state, navigate, selectSession]);

  useEffect(() => {
    void loadSandboxes();
    const timer = window.setInterval(() => void loadSandboxes(), SANDBOX_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadSandboxes]);

  const headerNode = useMemo(() => (
    <>
      <SandboxSelector
        containers={sandboxContainers}
        loading={sandboxLoading}
        value={sandboxContainerId}
        className="sandbox-selector-topbar"
        onChange={setSandboxContainerId}
      />
      <Button icon={<Plus size={16} />} theme="solid" type="primary" onClick={() => selectSession(null)}>
        New chat
      </Button>
      <span className={`stream-status stream-status-${status}`}>
        <Activity size={14} />
        <span>{STATUS_LABEL[status] ?? "Idle"}</span>
      </span>
    </>
  ), [sandboxContainerId, sandboxContainers, sandboxLoading, selectSession, status]);

  useEffect(() => {
    setHeaderActions(headerNode);
    return () => setHeaderActions(null);
  }, [headerNode, setHeaderActions]);

  const handleSend = async (text: string) => {
    try {
      await send(text, sandboxContainerId);
    } catch (error) {
      showApiError(error);
    }
  };

  return (
    <div className="playground-shell">
      <div className="playground-main">
        <div className="playground-canvas">
          <Spin spinning={historyLoading} wrapperClassName="playground-spin">
            <ChatStream
              nodes={chatState.nodes}
              streaming={chatState.streaming}
              agents={agents}
              followLatest={followLatest}
              onFollowLatestChange={setFollowLatest}
              onScrollToLatestReady={(handler) => {
                scrollToLatestRef.current = handler;
              }}
            />
          </Spin>
        </div>
        <div className="playground-composer">
          <Composer
            streaming={chatState.streaming}
            disabled={historyLoading}
            agents={agents}
            activeAgentCode={activeAgentCode}
            showScrollToLatest={!followLatest}
            onPickAgent={setActiveAgentCode}
            onScrollToLatest={() => scrollToLatestRef.current?.()}
            onSend={(text) => void handleSend(text)}
            onInterrupt={() => void interrupt()}
          />
        </div>
      </div>
    </div>
  );
}
