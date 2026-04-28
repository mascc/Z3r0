import { Button, Popconfirm, Tag } from "@douyinfe/semi-ui";
import { Ban, FolderKanban, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { cancelWorkProject, createWorkProject, deleteWorkProject, queryWorkProjects, retryWorkProject } from "../../shared/api/workProjects";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CreateWorkProjectRequest, WorkProject, WorkProjectStatus, WorkProjectType } from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { formatDateTime } from "../../shared/lib/date";
import { WorkProjectFormModal } from "./WorkProjectFormModal";

const DEFAULT_PAGE_SIZE = 10;
const statusColorMap = { working: "amber", completed: "green", failed: "red", canceled: "grey" } satisfies Record<WorkProjectStatus, "amber" | "green" | "red" | "grey">;
const typeColorMap = { penetration_test: "blue", source_code_audit: "cyan" } satisfies Record<WorkProjectType, "blue" | "cyan">;
const typeLabelMap = { penetration_test: "Penetration Test", source_code_audit: "Source Code Audit" } satisfies Record<WorkProjectType, string>;

type ModalState = { open: boolean };

function formatSessionId(sessionId: string) {
  return sessionId || "No session";
}

function formatDescription(description: string) {
  return description || "-";
}

export function WorkProjectsPage() {
  const {
    items: projects,
    page,
    keyword,
    loading,
    loadItems: loadProjects,
    setKeyword,
    search,
    previous,
    next,
    canGoBack,
    canGoNext,
  } = usePagedResourceList<WorkProject>({ pageSize: DEFAULT_PAGE_SIZE, query: queryWorkProjects });
  const [saving, setSaving] = useState(false);
  const [cancelingProjectId, setCancelingProjectId] = useState<number | null>(null);
  const [deletingProjectId, setDeletingProjectId] = useState<number | null>(null);
  const [retryingProjectId, setRetryingProjectId] = useState<number | null>(null);
  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const setHeaderActions = useAdminHeaderActions();

  useEffect(() => {
    setHeaderActions(
      <>
        <Button icon={<RefreshCw size={16} />} onClick={() => void loadProjects()} loading={loading} aria-label="Refresh work projects" />
        <Button icon={<Plus size={16} />} theme="solid" type="danger" onClick={() => setModalState({ open: true })}>
          Create Project
        </Button>
      </>,
    );
    return () => setHeaderActions(null);
  }, [loadProjects, loading, setHeaderActions]);

  const projectSummary = useMemo(
    () => projects.reduce(
      (summary, project) => ({
        working: summary.working + (project.status === "working" ? 1 : 0),
        completed: summary.completed + (project.status === "completed" ? 1 : 0),
        canceled: summary.canceled + (project.status === "canceled" ? 1 : 0),
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
      setModalState({ open: false });
      await loadProjects();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = async (project: WorkProject) => {
    if (cancelingProjectId !== null) {
      return;
    }

    setCancelingProjectId(project.id);
    try {
      const response = await cancelWorkProject(project.id);
      showApiSuccess(response);
      await loadProjects();
    } catch (error) {
      showApiError(error);
    } finally {
      setCancelingProjectId(null);
    }
  };

  const handleRetry = async (project: WorkProject) => {
    if (retryingProjectId !== null) {
      return;
    }

    setRetryingProjectId(project.id);
    try {
      const response = await retryWorkProject(project.id);
      showApiSuccess(response);
      await loadProjects();
    } catch (error) {
      showApiError(error);
    } finally {
      setRetryingProjectId(null);
    }
  };

  const handleDelete = async (project: WorkProject) => {
    if (deletingProjectId !== null) {
      return;
    }

    setDeletingProjectId(project.id);
    try {
      const response = await deleteWorkProject(project.id);
      showApiSuccess(response);
      await loadProjects();
    } catch (error) {
      showApiError(error);
    } finally {
      setDeletingProjectId(null);
    }
  };

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="Search project name, type, session, description, or status"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total loaded", value: projects.length },
          { label: "Working", value: projectSummary.working },
          { label: "Completed", value: projectSummary.completed },
          { label: "Canceled", value: projectSummary.canceled },
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
        <div className="resource-table work-projects-table" role="table" aria-label="Work projects">
          <div className="resource-table-row resource-table-head" role="row">
            <div role="columnheader">Project</div>
            <div role="columnheader">Type</div>
            <div role="columnheader">Status</div>
            <div role="columnheader">Description</div>
            <div role="columnheader">Created</div>
            <div role="columnheader">Updated</div>
            <div role="columnheader">Actions</div>
          </div>
          {projects.map((project) => (
            <div className="resource-table-row" role="row" key={project.id}>
              <div role="cell" className="project-identity">
                <div className="resource-avatar"><FolderKanban size={18} /></div>
                <div>
                  <strong>{project.name}</strong>
                  <span>{formatSessionId(project.session_id)}</span>
                </div>
              </div>
              <div role="cell"><Tag color={typeColorMap[project.type]}>{typeLabelMap[project.type]}</Tag></div>
              <div role="cell"><Tag color={statusColorMap[project.status]}>{project.status}</Tag></div>
              <div role="cell" className="resource-description">{formatDescription(project.description)}</div>
              <div role="cell">{formatDateTime(project.created_at)}</div>
              <div role="cell">{formatDateTime(project.updated_at)}</div>
              <div role="cell" className="row-actions">
                <Button
                  icon={<Ban size={15} />}
                  theme="borderless"
                  disabled={project.status !== "working"}
                  loading={cancelingProjectId === project.id}
                  aria-label={`Cancel ${project.name}`}
                  onClick={() => void handleCancel(project)}
                />
                <Button
                  icon={<RotateCcw size={15} />}
                  theme="borderless"
                  disabled={project.status !== "failed" && project.status !== "canceled"}
                  loading={retryingProjectId === project.id}
                  aria-label={`Retry ${project.name}`}
                  onClick={() => void handleRetry(project)}
                />
                <Popconfirm title="Delete project" content={`Delete ${project.name}?`} okType="danger" onConfirm={() => void handleDelete(project)}>
                  <Button
                    icon={<Trash2 size={15} />}
                    theme="borderless"
                    type="danger"
                    loading={deletingProjectId === project.id}
                    aria-label={`Delete ${project.name}`}
                  />
                </Popconfirm>
              </div>
            </div>
          ))}
        </div>
      </ResourcePageShell>

      <WorkProjectFormModal
        open={modalState.open}
        saving={saving}
        onCancel={() => setModalState({ open: false })}
        onSubmit={handleCreate}
      />
    </>
  );
}
