import { Button, Popconfirm, Tag } from "@douyinfe/semi-ui";
import { Pencil, Plus, RefreshCw, Trash2, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createSystemUser, deleteSystemUser, querySystemUsers, updateSystemUser } from "../../shared/api/systemUsers";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CreateSystemUserRequest, SystemUser, UpdateSystemUserRequest } from "../../shared/api/types";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
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
  const setHeaderActions = useAdminHeaderActions();

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

  useEffect(() => {
    setHeaderActions(
      <>
        <Button icon={<RefreshCw size={16} />} onClick={() => void loadUsers()} loading={loading} aria-label="Refresh users" />
        <Button icon={<Plus size={16} />} theme="solid" type="danger" onClick={() => setModalState({ open: true, mode: "create", user: null })}>
          Create User
        </Button>
      </>,
    );
    return () => setHeaderActions(null);
  }, [loadUsers, loading, setHeaderActions]);

  const roleSummary = useMemo(
    () => users.reduce(
      (summary, user) => ({
        admin: summary.admin + (user.role === "admin" ? 1 : 0),
        user: summary.user + (user.role === "user" ? 1 : 0),
      }),
      { admin: 0, user: 0 },
    ),
    [users],
  );

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
    <>
      <ResourcePageShell
        searchPlaceholder="Search username or email"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total loaded", value: users.length },
          { label: "Admins", value: roleSummary.admin },
          { label: "Operators", value: roleSummary.user },
        ]}
        empty={users.length === 0}
        emptyIcon={<Users size={42} />}
        emptyTitle="No users found"
        page={page}
        canGoBack={page > 1}
        canGoNext={users.length === DEFAULT_PAGE_SIZE}
        onKeywordChange={setKeyword}
        onSearch={() => { setPage(1); setActiveKeyword(keyword.trim()); }}
        onPrevious={() => setPage((current) => Math.max(1, current - 1))}
        onNext={() => setPage((current) => current + 1)}
      >
        <div className="resource-table system-users-table" role="table" aria-label="System users">
          <div className="resource-table-row resource-table-head" role="row">
            <div role="columnheader">User</div>
            <div role="columnheader">Role</div>
            <div role="columnheader">Created</div>
            <div role="columnheader">Updated</div>
            <div role="columnheader">Actions</div>
          </div>
          {users.map((user) => (
            <div className="resource-table-row" role="row" key={user.id}>
              <div role="cell" className="user-identity">
                <div className="resource-avatar">{user.username.slice(0, 1).toUpperCase()}</div>
                <div>
                  <strong>{user.username}</strong>
                  <span>{user.email || "-"}</span>
                </div>
              </div>
              <div role="cell"><Tag color={user.role === "admin" ? "red" : "blue"}>{user.role}</Tag></div>
              <div role="cell">{formatDateTime(user.created_at)}</div>
              <div role="cell">{formatDateTime(user.updated_at)}</div>
              <div role="cell" className="row-actions">
                <Button
                  icon={<Pencil size={15} />}
                  theme="borderless"
                  aria-label={`Edit ${user.username}`}
                  onClick={() => setModalState({ open: true, mode: "edit", user })}
                />
                <Popconfirm title="Delete user" content={`Delete ${user.username}?`} okType="danger" onConfirm={() => void handleDelete(user)}>
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
      </ResourcePageShell>

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
    </>
  );
}
