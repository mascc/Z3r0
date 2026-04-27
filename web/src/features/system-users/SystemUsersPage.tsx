import { Button, Empty, Input, Popconfirm, Spin, Tag } from "@douyinfe/semi-ui";
import { Pencil, Plus, RefreshCw, Search, Trash2, Users } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { createSystemUser, deleteSystemUser, querySystemUsers, updateSystemUser } from "../../shared/api/systemUsers";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CreateSystemUserRequest, SystemUser, UpdateSystemUserRequest } from "../../shared/api/types";
import { formatDateTime } from "../../shared/lib/date";
import { UserFormModal } from "./UserFormModal";

const DEFAULT_PAGE_SIZE = 10;

type ModalState =
  | { open: false; mode: "create"; user: null }
  | { open: true; mode: "create"; user: null }
  | { open: true; mode: "edit"; user: SystemUser };

export function SystemUsersPage() {
  const [users, setUsers] = useState<SystemUser[]>([]);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [activeKeyword, setActiveKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState<number | null>(null);
  const [modalState, setModalState] = useState<ModalState>({ open: false, mode: "create", user: null });

  const canGoBack = page > 1;
  const canGoNext = users.length === DEFAULT_PAGE_SIZE;

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const response = await querySystemUsers({ page, size: DEFAULT_PAGE_SIZE, keyword: activeKeyword });
      const items = response.data?.items || [];
      if (items.length === 0 && page > 1) {
        setPage((current) => Math.max(1, current - 1));
        return;
      }
      setUsers(items);
    } catch (error) {
      showApiError(error);
    } finally {
      setLoading(false);
    }
  }, [activeKeyword, page]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  const roleSummary = useMemo(() => {
    return users.reduce(
      (summary, user) => ({
        admin: summary.admin + (user.role === "admin" ? 1 : 0),
        user: summary.user + (user.role === "user" ? 1 : 0),
      }),
      { admin: 0, user: 0 },
    );
  }, [users]);

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPage(1);
    setActiveKeyword(keyword.trim());
  };

  const handleCreate = async (payload: CreateSystemUserRequest) => {
    setSaving(true);
    try {
      const response = await createSystemUser(payload);
      showApiSuccess(response);
      setModalState({ open: false, mode: "create", user: null });
      await loadUsers();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (user: SystemUser, payload: UpdateSystemUserRequest) => {
    setSaving(true);
    try {
      const response = await updateSystemUser(user.id, payload);
      showApiSuccess(response);
      setModalState({ open: false, mode: "create", user: null });
      await loadUsers();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (user: SystemUser) => {
    if (deletingUserId !== null) {
      return;
    }

    setDeletingUserId(user.id);
    try {
      const response = await deleteSystemUser(user.id);
      showApiSuccess(response);
      await loadUsers();
    } catch (error) {
      showApiError(error);
    } finally {
      setDeletingUserId(null);
    }
  };

  return (
    <section className="users-page">
      <div className="module-header">
        <div>
          <div className="module-kicker">Identity Surface</div>
          <h2>System Users</h2>
        </div>
        <div className="module-actions">
          <Button icon={<RefreshCw size={16} />} onClick={() => void loadUsers()} loading={loading} aria-label="Refresh users" />
          <Button icon={<Plus size={16} />} theme="solid" type="danger" onClick={() => setModalState({ open: true, mode: "create", user: null })}>
            Create User
          </Button>
        </div>
      </div>

      <div className="metric-strip">
        <div className="metric-card">
          <span>Total loaded</span>
          <strong>{users.length}</strong>
        </div>
        <div className="metric-card">
          <span>Admins</span>
          <strong>{roleSummary.admin}</strong>
        </div>
        <div className="metric-card">
          <span>Operators</span>
          <strong>{roleSummary.user}</strong>
        </div>
      </div>

      <div className="table-panel">
        <form className="table-toolbar" onSubmit={handleSearch}>
          <Input
            prefix={<Search size={16} />}
            value={keyword}
            onChange={setKeyword}
            placeholder="Search username or email"
            showClear
          />
          <Button htmlType="submit" theme="solid" type="primary" icon={<Search size={16} />}>
            Search
          </Button>
        </form>

        <Spin spinning={loading} wrapperClassName="users-table-spin">
          {users.length === 0 ? (
            <Empty className="empty-state" image={<Users size={42} />} title="No users found" description="" />
          ) : (
            <div className="users-table" role="table" aria-label="System users">
              <div className="users-table-row users-table-head" role="row">
                <div role="columnheader">User</div>
                <div role="columnheader">Role</div>
                <div role="columnheader">Created</div>
                <div role="columnheader">Updated</div>
                <div role="columnheader">Actions</div>
              </div>
              {users.map((user) => (
                <div className="users-table-row" role="row" key={user.id}>
                  <div role="cell" className="user-identity">
                    <div className="user-avatar">{user.username.slice(0, 1).toUpperCase()}</div>
                    <div>
                      <strong>{user.username}</strong>
                      <span>{user.email || "-"}</span>
                    </div>
                  </div>
                  <div role="cell">
                    <Tag color={user.role === "admin" ? "red" : "blue"}>{user.role}</Tag>
                  </div>
                  <div role="cell">{formatDateTime(user.created_at)}</div>
                  <div role="cell">{formatDateTime(user.updated_at)}</div>
                  <div role="cell" className="row-actions">
                    <Button
                      icon={<Pencil size={15} />}
                      theme="borderless"
                      aria-label={`Edit ${user.username}`}
                      onClick={() => setModalState({ open: true, mode: "edit", user })}
                    />
                    <Popconfirm
                      title="Delete user"
                      content={`Delete ${user.username}?`}
                      okType="danger"
                      onConfirm={() => void handleDelete(user)}
                    >
                      <Button
                        icon={<Trash2 size={15} />}
                        theme="borderless"
                        type="danger"
                        loading={deletingUserId === user.id}
                        aria-label={`Delete ${user.username}`}
                      />
                    </Popconfirm>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Spin>

        <div className="pager-row">
          <span>Page {page}</span>
          <div>
            <Button disabled={!canGoBack || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>
              Previous
            </Button>
            <Button disabled={!canGoNext || loading} onClick={() => setPage((current) => current + 1)}>
              Next
            </Button>
          </div>
        </div>
      </div>

      {modalState.mode === "edit" && modalState.user ? (
        <UserFormModal
          open={modalState.open}
          mode="edit"
          user={modalState.user}
          saving={saving}
          onCancel={() => setModalState({ open: false, mode: "create", user: null })}
          onSubmit={(payload) => handleUpdate(modalState.user, payload)}
        />
      ) : (
        <UserFormModal
          open={modalState.open}
          mode="create"
          user={null}
          saving={saving}
          onCancel={() => setModalState({ open: false, mode: "create", user: null })}
          onSubmit={handleCreate}
        />
      )}
    </section>
  );
}
