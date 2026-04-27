import { Avatar, Button } from "@douyinfe/semi-ui";
import { Boxes, LogOut, ShieldCheck, Users } from "lucide-react";
import { ReactNode, useCallback, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { useAuth } from "../../shared/auth/AuthProvider";

type HeaderActionsSetter = (actions: ReactNode) => void;

export function useAdminHeaderActions() {
  return useOutletContext<HeaderActionsSetter>();
}

const navItems = [
  {
    path: "/system-users",
    label: "System Users",
    eyebrow: "Access Control",
    icon: Users,
  },
  {
    path: "/sandbox-images",
    label: "Sandbox Images",
    eyebrow: "Execution Baseline",
    icon: Boxes,
  },
];

export function AdminLayout() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [headerActions, setHeaderActionsState] = useState<ReactNode>(null);

  const setHeaderActions = useCallback((actions: ReactNode) => {
    setHeaderActionsState(() => actions);
  }, []);

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
            <div className="brand-kicker">Operations Console</div>
          </div>
        </div>

        <nav className="admin-nav" aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.path} to={item.path} className="admin-nav-link">
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
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
          <Outlet context={setHeaderActions} />
        </main>
      </div>
    </div>
  );
}
