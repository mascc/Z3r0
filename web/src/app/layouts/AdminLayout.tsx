import { Avatar, Button } from "@douyinfe/semi-ui";
import { LogOut, ShieldCheck, Users } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../shared/auth/AuthProvider";

const navItems = [
  {
    path: "/system-users",
    label: "System Users",
    icon: Users,
  },
];

export function AdminLayout() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

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
            <div className="page-eyebrow">Access Control</div>
            <h1>{activeItem?.label || "Console"}</h1>
          </div>
          <div className="topbar-actions">
            <div className="signal-pill">
              <span /> Secure session
            </div>
            <Avatar size="small" color="red">A</Avatar>
            <Button icon={<LogOut size={16} />} theme="borderless" onClick={handleSignOut} aria-label="Sign out" />
          </div>
        </header>
        <main className="admin-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
