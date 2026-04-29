import { Button, Popconfirm, Tag } from "@douyinfe/semi-ui";
import { Ban, FolderKanban, Play, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { useAgentSessionContext } from "../playground/AgentSessionProvider";
import { cancelWorkProject, createWorkProject, deleteWorkProject, queryWorkProjects, retryWorkProject } from "../../shared/api/workProjects";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CreateWorkProjectRequest, WorkProject } from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceAction } from "../../shared/hooks/useResourceAction";
import { formatDateTime } from "../../shared/lib/date";
import {
  WORK_PROJECT_STATUS_COLOR,
  WORK_PROJECT_STATUS_LABEL,
  WORK_PROJECT_TYPE_COLOR,
  WORK_PROJECT_TYPE_LABEL,
} from "../../shared/lib/labels";
import { WorkProjectFormModal } from "./WorkProjectFormModal";

const DEFAULT_PAGE_SIZE = 10;

export function WorkProjectsPage() {
  const {
    items: projects, page, keyword, loading, loadItems: loadProjects,
    setKeyword, search, previous, next, canGoBack, canGoNext,
  } = usePagedResourceList<WorkProject>({ pageSize: DEFAULT_PAGE_SIZE, query: queryWorkProjects });
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const setHeaderActions = useAdminHeaderActions();
  const { refreshSessions } = useAgentSessionContext();
  const navigate = useNavigate();

  const refreshAll = useCallback(async () => {
    await loadProjects();
    await refreshSessions();
  }, [loadProjects, refreshSessions]);

  const { run: cancelProject, busyId: cancelingId } = useResourceAction<WorkProject>(
    (project) => cancelWorkProject(project.id), loadProjects,
  );
  const { run: retryProject, busyId: retryingId } = useResourceAction<WorkProject>(
    (project) => retryWorkProject(project.id), loadProjects,
  );
  const { run: deleteProject, busyId: deletingId } = useResourceAction<WorkProject>(
    (project) => deleteWorkProject(project.id), refreshAll,
  );

  useEffect(() => {
    setHeaderActions(
      <>
        <Button icon={<RefreshCw size={16} />} onClick={() => void loadProjects()} loading={loading} aria-label="Refresh work projects" />
        <Button icon={<Plus size={16} />} theme="solid" type="danger" onClick={() => setModalOpen(true)}>
          Create Project
        </Button>
      </>,
    );
    return () => setHeaderActions(null);
  }, [loadProjects, loading, setHeaderActions]);

  const summary = useMemo(
    () => projects.reduce(
      (acc, project) => ({
        working: acc.working + (project.status === "working" ? 1 : 0),
        completed: acc.completed + (project.status === "completed" ? 1 : 0),
        canceled: acc.canceled + (project.status === "canceled" ? 1 : 0),
      }),
      { working: 0, completed: 0, canceled: 0 },
    ),
    [projects],
  );

  const handleCreate = async (payload: CreateWorkProjectRequest) => {
    setSaving(true);
    try {
      const response = await createWorkProject(payload);
      showApiSuccess(response);
      setModalOpen(false);
      await refreshAll();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
    }
  };

  const columns: ResourceColumn<WorkProject>[] = [
    {
      key: "project", header: "Project", width: "minmax(176px, 0.9fr)",
      render: (project) => (
        <div className="project-identity">
          <div className="resource-avatar"><FolderKanban size={18} /></div>
          <div>
            <strong>{project.name}</strong>
            <span title={project.session_id || undefined}>{project.session_id || "No session"}</span>
          </div>
        </div>
      ),
    },
    {
      key: "type", header: "Type", width: "124px",
      render: (project) => (
        <Tag color={WORK_PROJECT_TYPE_COLOR[project.type]}>{WORK_PROJECT_TYPE_LABEL[project.type]}</Tag>
      ),
    },
    {
      key: "status", header: "Status", width: "100px",
      render: (project) => (
        <Tag color={WORK_PROJECT_STATUS_COLOR[project.status]}>{WORK_PROJECT_STATUS_LABEL[project.status]}</Tag>
      ),
    },
    {
      key: "description", header: "Description", width: "minmax(0, 0.7fr)",
      render: (project) => <div className="resource-description">{project.description || "-"}</div>,
    },
    { key: "created", header: "Created", width: "minmax(150px, 0.5fr)", render: (p) => formatDateTime(p.created_at) },
    { key: "updated", header: "Updated", width: "minmax(150px, 0.5fr)", render: (p) => formatDateTime(p.updated_at) },
    {
      key: "actions", header: "Actions", width: "106px",
      render: (project) => (
        <div className="row-actions">
          <Button icon={<Play size={15} />} theme="borderless" type="primary"
            disabled={!project.session_id} aria-label={`Open ${project.name} in playground`}
            onClick={() => navigate("/playground", { state: { sessionId: project.session_id } })}
          />
          <Button icon={<Ban size={15} />} theme="borderless"
            disabled={project.status !== "working"} loading={cancelingId === project.id}
            aria-label={`Cancel ${project.name}`} onClick={() => void cancelProject(project)}
          />
          <Button icon={<RotateCcw size={15} />} theme="borderless"
            disabled={project.status !== "failed" && project.status !== "canceled"}
            loading={retryingId === project.id}
            aria-label={`Retry ${project.name}`} onClick={() => void retryProject(project)}
          />
          <Popconfirm title="Delete project" content={`Delete ${project.name}?`} okType="danger" onConfirm={() => void deleteProject(project)}>
            <Button icon={<Trash2 size={15} />} theme="borderless" type="danger"
              loading={deletingId === project.id} aria-label={`Delete ${project.name}`}
            />
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="Search project name, type, session, description, or status"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total loaded", value: projects.length },
          { label: "Working", value: summary.working },
          { label: "Completed", value: summary.completed },
          { label: "Canceled", value: summary.canceled },
        ]}
        empty={projects.length === 0}
        emptyIcon={<FolderKanban size={42} />}
        emptyTitle="No projects found"
        page={page}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        onKeywordChange={setKeyword}
        onSearch={search}
        onPrevious={previous}
        onNext={next}
      >
        <ResourceTable<WorkProject>
          ariaLabel="Work projects"
          className="work-projects-table"
          columns={columns}
          rows={projects}
          rowKey={(project) => project.id}
        />
      </ResourcePageShell>

      <WorkProjectFormModal
        open={modalOpen}
        saving={saving}
        onCancel={() => setModalOpen(false)}
        onSubmit={handleCreate}
      />
    </>
  );
}
