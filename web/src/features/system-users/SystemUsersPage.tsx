import { Button, Popconfirm, Tag } from "@douyinfe/semi-ui";
import { Pencil, Plus, RefreshCw, Trash2, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createSystemUser, deleteSystemUser, querySystemUsers, updateSystemUser } from "../../shared/api/systemUsers";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CommonResponsePayload, CreateSystemUserRequest, SystemUser, UpdateSystemUserRequest } from "../../shared/api/types";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceAction } from "../../shared/hooks/useResourceAction";
import { formatDateTime } from "../../shared/lib/date";
import { UserFormModal } from "./UserFormModal";

const DEFAULT_PAGE_SIZE = 10;

type ModalState = { mode: "create" } | { mode: "edit"; user: SystemUser } | null;

export function SystemUsersPage() {
  const {
    items: users,
    page,
    keyword,
    loading,
    loadItems: loadUsers,
    setKeyword,
    search,
    previous,
    next,
    canGoBack,
    canGoNext,
  } = usePagedResourceList<SystemUser>({ pageSize: DEFAULT_PAGE_SIZE, query: querySystemUsers });
  const [saving, setSaving] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);
  const setHeaderActions = useAdminHeaderActions();
  const { run: deleteUser, busyId: deletingUserId } = useResourceAction<SystemUser>(
    (user) => deleteSystemUser(user.id),
    loadUsers,
  );

  useEffect(() => {
    setHeaderActions(
      <>
        <Button icon={<RefreshCw size={16} />} onClick={() => void loadUsers()} loading={loading} aria-label="Refresh users" />
        <Button icon={<Plus size={16} />} theme="solid" type="danger" onClick={() => setModal({ mode: "create" })}>
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

  const submit = async (action: () => Promise<CommonResponsePayload>) => {
    setSaving(true);
    try {
      const response = await action();
      showApiSuccess(response);
      setModal(null);
      await loadUsers();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
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
          { label: "Users", value: roleSummary.user },
        ]}
        empty={users.length === 0}
        emptyIcon={<Users size={42} />}
        emptyTitle="No users found"
        page={page}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        onKeywordChange={setKeyword}
        onSearch={search}
        onPrevious={previous}
        onNext={next}
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
                  onClick={() => setModal({ mode: "edit", user })}
                />
                <Popconfirm title="Delete user" content={`Delete ${user.username}?`} okType="danger" onConfirm={() => void deleteUser(user)}>
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

      {modal?.mode === "edit" ? (
        <UserFormModal
          open
          mode="edit"
          user={modal.user}
          saving={saving}
          onCancel={() => setModal(null)}
          onSubmit={(payload: UpdateSystemUserRequest) => submit(() => updateSystemUser(modal.user.id, payload))}
        />
      ) : (
        <UserFormModal
          open={modal?.mode === "create"}
          mode="create"
          user={null}
          saving={saving}
          onCancel={() => setModal(null)}
          onSubmit={(payload: CreateSystemUserRequest) => submit(() => createSystemUser(payload))}
        />
      )}
    </>
  );
}
