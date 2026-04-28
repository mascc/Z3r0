import { Avatar, Button } from "@douyinfe/semi-ui";
import { Boxes, FolderKanban, LogOut, MessageSquareCode, ShieldCheck, Users } from "lucide-react";
import { ReactNode, useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { SessionList } from "../../features/playground/SessionList";
import { useAgentSession } from "../../features/playground/useAgentSession";
import { deleteAgentSession, listAgentSessions } from "../../shared/api/agentSessions";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { AgentSessionSummary } from "../../shared/api/types";
import { useAuth } from "../../shared/auth/AuthProvider";

type AgentSessionRuntime = ReturnType<typeof useAgentSession>;

type AdminLayoutContext = {
  setHeaderActions: (actions: ReactNode) => void;
  activeAgentSessionId: string | null;
  setActiveAgentSessionId: (sessionId: string | null) => void;
  refreshAgentSessions: () => Promise<void>;
  agentSession: AgentSessionRuntime;
};

export function useAdminHeaderActions() {
  return useOutletContext<AdminLayoutContext>().setHeaderActions;
}

export function useAdminAgentSession() {
  const { activeAgentSessionId, setActiveAgentSessionId, refreshAgentSessions, agentSession } = useOutletContext<AdminLayoutContext>();
  return { activeAgentSessionId, setActiveAgentSessionId, refreshAgentSessions, agentSession };
}

const navItems = [
  {
    path: "/playground",
    label: "Playground",
    eyebrow: "Agent Workbench",
    icon: MessageSquareCode,
  },
  {
    path: "/work-projects",
    label: "Work Projects",
    eyebrow: "Project Operations",
    icon: FolderKanban,
  },
  {
    path: "/sandbox-images",
    label: "Sandbox Images",
    eyebrow: "Execution Baseline",
    icon: Boxes,
  },
  {
    path: "/system-users",
    label: "System Users",
    eyebrow: "Access Control",
    icon: Users,
  },
];

export function AdminLayout() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [headerActions, setHeaderActionsState] = useState<ReactNode>(null);
  const [agentSessions, setAgentSessions] = useState<AgentSessionSummary[]>([]);
  const [agentSessionsLoading, setAgentSessionsLoading] = useState(false);
  const [activeAgentSessionId, setActiveAgentSessionId] = useState<string | null>(null);
  const agentSession = useAgentSession(activeAgentSessionId);

  const setHeaderActions = useCallback((actions: ReactNode) => {
    setHeaderActionsState(() => actions);
  }, []);

  const refreshAgentSessions = useCallback(async () => {
    setAgentSessionsLoading(true);
    try {
      const response = await listAgentSessions();
      setAgentSessions(response.data?.items ?? []);
    } catch (error) {
      showApiError(error);
    } finally {
      setAgentSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshAgentSessions();
  }, [refreshAgentSessions]);

  const handleSelectAgentSession = useCallback((sessionId: string) => {
    setActiveAgentSessionId(sessionId);
    if (!location.pathname.startsWith("/playground")) {
      navigate("/playground", { state: { sessionId } });
    }
  }, [location.pathname, navigate]);

  const handleDeleteAgentSession = useCallback(async (sessionId: string) => {
    try {
      const response = await deleteAgentSession(sessionId);
      showApiSuccess(response);
      if (activeAgentSessionId === sessionId) {
        setActiveAgentSessionId(null);
      }
      await refreshAgentSessions();
    } catch (error) {
      showApiError(error);
    }
  }, [activeAgentSessionId, refreshAgentSessions]);

  const outletContext: AdminLayoutContext = {
    setHeaderActions,
    activeAgentSessionId,
    setActiveAgentSessionId,
    refreshAgentSessions,
    agentSession,
  };

  const handleSignOut = () => {
    signOut();
    navigate("/login", { replace: true });
  };

  const activeItem = navItems.find((item) => location.pathname.startsWith(item.path));

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">
            <ShieldCheck size={22} />
          </div>
          <div>
            <div className="brand-name">Z3r0</div>
            <div className="brand-kicker">Red Team Collaboration Platform</div>
          </div>
        </div>

        <div className="admin-sidebar-body">
          <div className="admin-sidebar-top">
            <NavLink to="/playground" className="admin-nav-link">
              <MessageSquareCode size={18} />
              <span>Playground</span>
            </NavLink>
            <div className="admin-sidebar-secondary">
              <SessionList
                sessions={agentSessions}
                loading={agentSessionsLoading}
                activeSessionId={activeAgentSessionId}
                onSelect={handleSelectAgentSession}
                onDelete={handleDeleteAgentSession}
              />
            </div>
          </div>

          <nav className="admin-nav admin-nav-bottom" aria-label="Primary navigation">
            {navItems.slice(1).map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.path} to={item.path} className="admin-nav-link">
                  <Icon size={18} />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>
      </aside>

      <div className="admin-main">
        <header className="admin-topbar">
          <div>
            <div className="page-eyebrow">{activeItem?.eyebrow || "Operations"}</div>
            <h1>{activeItem?.label || "Console"}</h1>
          </div>
          <div className="topbar-actions">
            {headerActions ? <div className="topbar-resource-actions">{headerActions}</div> : null}
            <div className="topbar-session-actions">
              <div className="signal-pill">
                <span /> Secure session
              </div>
              <Avatar size="small" color="red">A</Avatar>
              <Button icon={<LogOut size={16} />} theme="borderless" onClick={handleSignOut} aria-label="Sign out" />
            </div>
          </div>
        </header>
        <main className="admin-content">
          <Outlet context={outletContext} />
        </main>
      </div>
    </div>
  );
}
