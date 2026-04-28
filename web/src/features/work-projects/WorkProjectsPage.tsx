import { Button, Popconfirm, Tag } from "@douyinfe/semi-ui";
import type { TagColor } from "@douyinfe/semi-ui/lib/es/tag";
import { Ban, FolderKanban, Play, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAdminAgentSession, useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { cancelWorkProject, createWorkProject, deleteWorkProject, queryWorkProjects, retryWorkProject } from "../../shared/api/workProjects";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CreateWorkProjectRequest, WorkProject, WorkProjectStatus, WorkProjectType } from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceAction } from "../../shared/hooks/useResourceAction";
import { formatDateTime } from "../../shared/lib/date";
import { WorkProjectFormModal } from "./WorkProjectFormModal";

const DEFAULT_PAGE_SIZE = 10;
const statusColorMap: Record<WorkProjectStatus, TagColor> = { working: "amber", completed: "green", failed: "red", canceled: "grey" };
const typeColorMap: Record<WorkProjectType, TagColor> = { penetration_test: "blue", source_code_audit: "cyan" };
const typeLabelMap: Record<WorkProjectType, string> = { penetration_test: "Penetration Test", source_code_audit: "Source Code Audit" };

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
  const [modalOpen, setModalOpen] = useState(false);
  const setHeaderActions = useAdminHeaderActions();
  const { refreshAgentSessions } = useAdminAgentSession();
  const navigate = useNavigate();

  const refreshProjectsAndSessions = useCallback(async () => {
    await loadProjects();
    await refreshAgentSessions();
  }, [loadProjects, refreshAgentSessions]);

  const { run: cancelProject, busyId: cancelingId } = useResourceAction<WorkProject>(
    (project) => cancelWorkProject(project.id),
    loadProjects,
  );
  const { run: retryProject, busyId: retryingId } = useResourceAction<WorkProject>(
    (project) => retryWorkProject(project.id),
    loadProjects,
  );
  const { run: deleteProject, busyId: deletingId } = useResourceAction<WorkProject>(
    (project) => deleteWorkProject(project.id),
    refreshProjectsAndSessions,
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
      setModalOpen(false);
      await refreshProjectsAndSessions();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
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
                  <span>{project.session_id || "No session"}</span>
                </div>
              </div>
              <div role="cell"><Tag color={typeColorMap[project.type]}>{typeLabelMap[project.type]}</Tag></div>
              <div role="cell"><Tag color={statusColorMap[project.status]}>{project.status}</Tag></div>
              <div role="cell" className="resource-description">{project.description || "-"}</div>
              <div role="cell">{formatDateTime(project.created_at)}</div>
              <div role="cell">{formatDateTime(project.updated_at)}</div>
              <div role="cell" className="row-actions">
                <Button
                  icon={<Play size={15} />}
                  theme="borderless"
                  type="primary"
                  disabled={!project.session_id}
                  aria-label={`Open ${project.name} in playground`}
                  onClick={() => navigate("/playground", { state: { sessionId: project.session_id } })}
                />
                <Button
                  icon={<Ban size={15} />}
                  theme="borderless"
                  disabled={project.status !== "working"}
                  loading={cancelingId === project.id}
                  aria-label={`Cancel ${project.name}`}
                  onClick={() => void cancelProject(project)}
                />
                <Button
                  icon={<RotateCcw size={15} />}
                  theme="borderless"
                  disabled={project.status !== "failed" && project.status !== "canceled"}
                  loading={retryingId === project.id}
                  aria-label={`Retry ${project.name}`}
                  onClick={() => void retryProject(project)}
                />
                <Popconfirm title="Delete project" content={`Delete ${project.name}?`} okType="danger" onConfirm={() => void deleteProject(project)}>
                  <Button
                    icon={<Trash2 size={15} />}
                    theme="borderless"
                    type="danger"
                    loading={deletingId === project.id}
                    aria-label={`Delete ${project.name}`}
                  />
                </Popconfirm>
              </div>
            </div>
          ))}
        </div>
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
