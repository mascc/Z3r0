import { Button, Input, Modal, Popconfirm, Spin } from "@douyinfe/semi-ui";
import { ChevronDown, ChevronRight, Edit3, FolderKanban, Info, MessageCircle, MessageSquarePlus, Play, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { updateAgentSessionTitle } from "../../shared/api/agentSessions";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import {
  createWorkProjectSession,
  deleteWorkProjectSession,
  getWorkProject,
  listWorkProjectSessions,
  queryWorkProjects,
} from "../../shared/api/workProjects";
import type { AgentSessionSummary, WorkProject } from "../../shared/api/types";
import { WorkProjectInfoModal } from "./WorkProjectInfoModal";

const PROJECT_REFRESH_INTERVAL_MS = 5000;

type SessionListProps = {
  sessions: AgentSessionSummary[];
  loading: boolean;
  activeSessionId: string | null;
  canDeleteProjectSession: boolean;
  projectListVersion: number;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onRefreshSessions: () => Promise<void>;
  onDropRuntime: (sessionId: string) => void;
  onEnsureRuntime: (sessionId: string) => void;
};

type ProjectSessionState = {
  loading: boolean;
  items: AgentSessionSummary[];
};

type ChatSessionRowProps = {
  session: AgentSessionSummary;
  active: boolean;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onRename: (session: AgentSessionSummary) => void;
};

type ProjectGroupProps = {
  project: WorkProject;
  state?: ProjectSessionState;
  expanded: boolean;
  activeSessionId: string | null;
  canDeleteProjectSession: boolean;
  onToggle: (projectId: number) => void;
  onShowInfo: (project: WorkProject) => void;
  onCreateSession: (project: WorkProject) => void;
  onSelectSession: (sessionId: string) => void;
  onRenameSession: (session: AgentSessionSummary, projectId: number) => void;
  onDeleteSession: (projectId: number, sessionId: string) => void;
};

type RenameTarget = {
  session: AgentSessionSummary;
  projectId?: number;
};

export function SessionList({
  sessions,
  loading,
  activeSessionId,
  canDeleteProjectSession,
  projectListVersion,
  onSelect,
  onDelete,
  onRefreshSessions,
  onDropRuntime,
  onEnsureRuntime,
}: SessionListProps) {
  const [projects, setProjects] = useState<WorkProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [expandedProjectId, setExpandedProjectId] = useState<number | null>(null);
  const [projectSessions, setProjectSessions] = useState<Map<number, ProjectSessionState>>(() => new Map());
  const [infoOpen, setInfoOpen] = useState(false);
  const [infoLoading, setInfoLoading] = useState(false);
  const [infoProject, setInfoProject] = useState<WorkProject | null>(null);
  const [renameTarget, setRenameTarget] = useState<RenameTarget | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [renaming, setRenaming] = useState(false);

  const loadProjects = useCallback(async (silent = false) => {
    if (!silent) setProjectsLoading(true);
    try {
      const response = await queryWorkProjects({ page: 1, size: 100, keyword: "" });
      setProjects(response.data?.items ?? []);
    } catch (error) {
      if (!silent) showApiError(error);
    } finally {
      if (!silent) setProjectsLoading(false);
    }
  }, []);

  const loadProjectSessions = useCallback(async (projectId: number, silent = false) => {
    if (!silent) {
      setProjectSessions((prev) => new Map(prev).set(projectId, {
        loading: true,
        items: prev.get(projectId)?.items ?? [],
      }));
    }
    try {
      const response = await listWorkProjectSessions(projectId);
      const items = response.data?.items ?? [];
      setProjectSessions((prev) => new Map(prev).set(projectId, {
        loading: false,
        items,
      }));
      items.forEach((session) => {
        if (session.is_running) onEnsureRuntime(session.session_id);
      });
    } catch (error) {
      if (!silent) showApiError(error);
      if (!silent) {
        setProjectSessions((prev) => new Map(prev).set(projectId, {
          loading: false,
          items: prev.get(projectId)?.items ?? [],
        }));
      }
    }
  }, [onEnsureRuntime]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects, projectListVersion]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadProjects(true);
      if (expandedProjectId) void loadProjectSessions(expandedProjectId, true);
    }, PROJECT_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [expandedProjectId, loadProjectSessions, loadProjects]);

  const toggleProject = (projectId: number) => {
    const nextProjectId = expandedProjectId === projectId ? null : projectId;
    setExpandedProjectId(nextProjectId);
    if (nextProjectId) void loadProjectSessions(nextProjectId);
  };

  const createProjectSession = async (project: WorkProject) => {
    try {
      const response = await createWorkProjectSession(project.id);
      const sessionId = response.data?.session_id;
      if (!sessionId) return;
      showApiSuccess(response);
      await loadProjectSessions(project.id);
      onSelect(sessionId);
    } catch (error) {
      showApiError(error);
    }
  };

  const deleteProjectSession = async (projectId: number, sessionId: string) => {
    try {
      const response = await deleteWorkProjectSession(projectId, sessionId);
      showApiSuccess(response);
      onDropRuntime(sessionId);
      await loadProjectSessions(projectId);
    } catch (error) {
      showApiError(error);
    }
  };

  const openRename = (target: RenameTarget) => {
    setRenameTarget(target);
    setRenameTitle(target.session.title || "");
  };

  const saveRename = async () => {
    const title = renameTitle.trim();
    if (!renameTarget || !title) return;
    setRenaming(true);
    try {
      const response = await updateAgentSessionTitle(renameTarget.session.session_id, { title });
      showApiSuccess(response);
      setRenameTarget(null);
      setRenameTitle("");
      if (renameTarget.projectId) {
        await loadProjectSessions(renameTarget.projectId, true);
      } else {
        await onRefreshSessions();
      }
    } catch (error) {
      showApiError(error);
    } finally {
      setRenaming(false);
    }
  };

  const showProjectInfo = async (project: WorkProject) => {
    setInfoOpen(true);
    setInfoProject(project);
    setInfoLoading(true);
    try {
      const response = await getWorkProject(project.id);
      setInfoProject(response.data ?? project);
    } catch (error) {
      showApiError(error);
    } finally {
      setInfoLoading(false);
    }
  };

  const empty = sessions.length === 0 && projects.length === 0 && !loading && !projectsLoading;

  return (
    <div className="session-list">
      <div className="session-list-body">
        <Spin spinning={loading || projectsLoading} wrapperClassName="session-list-spin">
          {empty ? (
            <div className="session-empty">
              <MessageCircle size={28} />
              <p>No conversations yet.</p>
            </div>
          ) : (
            <>
              {sessions.map((session) => (
                <ChatSessionRow
                  key={session.session_id}
                  session={session}
                  active={session.session_id === activeSessionId}
                  onSelect={onSelect}
                  onDelete={onDelete}
                  onRename={(targetSession) => openRename({ session: targetSession })}
                />
              ))}
              {projects.map((project) => (
                <ProjectGroup
                  key={project.id}
                  project={project}
                  state={projectSessions.get(project.id)}
                  expanded={expandedProjectId === project.id}
                  activeSessionId={activeSessionId}
                  canDeleteProjectSession={canDeleteProjectSession}
                  onToggle={toggleProject}
                  onShowInfo={(targetProject) => void showProjectInfo(targetProject)}
                  onCreateSession={(targetProject) => void createProjectSession(targetProject)}
                  onSelectSession={onSelect}
                  onRenameSession={(targetSession, projectId) => openRename({ session: targetSession, projectId })}
                  onDeleteSession={(projectId, sessionId) => void deleteProjectSession(projectId, sessionId)}
                />
              ))}
            </>
          )}
        </Spin>
      </div>
      <WorkProjectInfoModal
        open={infoOpen}
        loading={infoLoading}
        project={infoProject}
        onClose={() => setInfoOpen(false)}
      />
      <Modal
        visible={Boolean(renameTarget)}
        title="Edit Session Title"
        okText="Save"
        confirmLoading={renaming}
        okButtonProps={{ disabled: !renameTitle.trim() }}
        onOk={() => void saveRename()}
        onCancel={() => setRenameTarget(null)}
      >
        <Input
          autoFocus
          maxLength={80}
          value={renameTitle}
          onChange={setRenameTitle}
          onEnterPress={() => void saveRename()}
        />
      </Modal>
    </div>
  );
}

function ChatSessionRow({ session, active, onSelect, onDelete, onRename }: ChatSessionRowProps) {
  return (
    <div className={`session-row${active ? " session-row-active" : ""}`}>
      <button type="button" className="session-row-main" onClick={() => onSelect(session.session_id)}>
        <span className="session-row-icon"><MessageCircle size={14} /></span>
        <span className="session-row-body">
          <span className="session-row-title">{session.title || "Untitled session"}</span>
        </span>
      </button>
      <Button
        icon={<Edit3 size={14} />}
        theme="borderless"
        size="small"
        aria-label={`Edit ${session.title || session.session_id}`}
        onClick={() => onRename(session)}
      />
      <Popconfirm
        title="Delete chat"
        content="Permanently delete this conversation?"
        okType="danger"
        onConfirm={() => onDelete(session.session_id)}
      >
        <Button
          icon={<Trash2 size={14} />}
          theme="borderless"
          type="danger"
          size="small"
          aria-label={`Delete ${session.title || session.session_id}`}
        />
      </Popconfirm>
    </div>
  );
}

function ProjectGroup({
  project,
  state,
  expanded,
  activeSessionId,
  canDeleteProjectSession,
  onToggle,
  onShowInfo,
  onCreateSession,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
}: ProjectGroupProps) {
  return (
    <div className="session-project-group">
      <div className="session-row session-row-project">
        <button type="button" className="session-row-main" onClick={() => onToggle(project.id)}>
          <span className="session-row-icon">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          <span className="session-row-body">
            <span className="session-row-title">{project.name}</span>
          </span>
        </button>
        <Button
          icon={<Info size={14} />}
          theme="borderless"
          size="small"
          aria-label={`View ${project.name} details`}
          onClick={() => onShowInfo(project)}
        />
        <Button
          icon={<MessageSquarePlus size={14} />}
          theme="borderless"
          type="primary"
          size="small"
          disabled={!project.can_create_session}
          aria-label={`Create session for ${project.name}`}
          onClick={() => onCreateSession(project)}
        />
      </div>

      {expanded ? (
        <div className="session-project-children">
          {state?.loading ? <div className="session-project-empty">Loading sessions...</div> : null}
          {!state?.loading && (!state || state.items.length === 0) ? (
            <button
              type="button"
              className="session-project-empty"
              disabled={!project.can_create_session}
              onClick={() => onCreateSession(project)}
            >
              <FolderKanban size={14} />
              <span>New project session</span>
            </button>
          ) : null}
          {state?.items.map((session) => (
            <ProjectSessionRow
              key={session.session_id}
              session={session}
              projectId={project.id}
              active={session.session_id === activeSessionId}
              canDelete={canDeleteProjectSession}
              onSelect={onSelectSession}
              onRename={onRenameSession}
              onDelete={onDeleteSession}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ProjectSessionRow({
  session,
  projectId,
  active,
  canDelete,
  onSelect,
  onRename,
  onDelete,
}: {
  session: AgentSessionSummary;
  projectId: number;
  active: boolean;
  canDelete: boolean;
  onSelect: (sessionId: string) => void;
  onRename: (session: AgentSessionSummary, projectId: number) => void;
  onDelete: (projectId: number, sessionId: string) => void;
}) {
  return (
    <div className={`session-row session-row-project-session${active ? " session-row-active" : ""}`}>
      <button type="button" className="session-row-main" onClick={() => onSelect(session.session_id)}>
        <span className="session-row-icon"><Play size={13} /></span>
        <span className="session-row-body">
          <span className="session-row-title">{session.title || "Project session"}</span>
        </span>
      </button>
      <Button
        icon={<Edit3 size={14} />}
        theme="borderless"
        size="small"
        aria-label={`Edit ${session.title || session.session_id}`}
        onClick={() => onRename(session, projectId)}
      />
      {canDelete ? (
        <Popconfirm
          title="Delete session"
          content="Permanently delete this project session?"
          okType="danger"
          onConfirm={() => onDelete(projectId, session.session_id)}
        >
          <Button
            icon={<Trash2 size={14} />}
            theme="borderless"
            type="danger"
            size="small"
            aria-label={`Delete ${session.title || session.session_id}`}
          />
        </Popconfirm>
      ) : null}
    </div>
  );
}
