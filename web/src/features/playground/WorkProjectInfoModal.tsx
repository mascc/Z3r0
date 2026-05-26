import { Modal, Progress, Spin } from "@douyinfe/semi-ui";
import { ClipboardList, FolderKanban, UserRound } from "lucide-react";
import type { WorkProject } from "../../shared/api/types";
import {
  WorkProjectAssets,
  WorkProjectPanel,
  WorkProjectStatusTag,
  WorkProjectSummaries,
  WorkProjectTasks,
  WorkProjectTypeTag,
  workProjectAssetLines,
  workProjectOwnerNames,
} from "../work-projects/workProjectView";

type WorkProjectInfoModalProps = {
  open: boolean;
  loading: boolean;
  project: WorkProject | null;
  onClose: () => void;
};

export function WorkProjectInfoModal({ open, loading, project, onClose }: WorkProjectInfoModalProps) {
  const assets = project ? workProjectAssetLines(project) : [];

  return (
    <Modal
      visible={open}
      title={<ProjectInfoTitle project={project} />}
      width="min(1180px, calc(100vw - 32px))"
      footer={null}
      onCancel={onClose}
    >
      <Spin spinning={loading}>
        {project ? (
          <div className={`project-info-content${project.description ? " project-info-content-described" : ""}`}>
            {project.description ? <div className="project-info-description">{project.description}</div> : null}

            <div className="project-info-main">
              <section className="project-info-meta">
                <div>
                  <span>Type</span>
                  <WorkProjectTypeTag project={project} />
                </div>
                <div>
                  <span>Status</span>
                  <WorkProjectStatusTag project={project} />
                </div>
                <div>
                  <span>Owners</span>
                  <strong>{workProjectOwnerNames(project)}</strong>
                </div>
                <div>
                  <span>Sandbox</span>
                  <strong>{project.sandbox_container_id ?? "-"}</strong>
                </div>
              </section>

              <section className="project-info-progress">
                <span>Task Progress</span>
                <Progress percent={project.progress} size="small" showInfo />
              </section>

              <section className="project-info-grid">
                <WorkProjectPanel
                  title="Target Assets"
                  icon={<FolderKanban size={15} />}
                  empty={!assets.length ? "No data." : ""}
                  className="project-info-panel"
                  emptyClassName="project-info-empty"
                >
                  <WorkProjectAssets project={project} className="project-info-scroll-list project-info-assets" />
                </WorkProjectPanel>

                <WorkProjectPanel
                  title="Tasks"
                  icon={<ClipboardList size={15} />}
                  empty={!project.tasks.length ? "No data." : ""}
                  className="project-info-panel"
                  emptyClassName="project-info-empty"
                >
                  <WorkProjectTasks project={project} className="project-info-scroll-list project-info-tasks" rowClassName="project-info-task-row" />
                </WorkProjectPanel>
              </section>
            </div>

            <WorkProjectPanel
              title="Agent Summaries"
              icon={<UserRound size={15} />}
              empty={!project.agent_summaries.length ? "No data." : ""}
              className="project-info-panel project-info-summary-panel"
              emptyClassName="project-info-empty"
            >
              <WorkProjectSummaries
                project={project}
                className="project-info-scroll-list project-info-summaries project-info-summary-scroll"
                rowClassName="project-info-summary"
                progressClassName="project-info-summary-task"
                blockClassName="project-info-summary-block"
              />
            </WorkProjectPanel>
          </div>
        ) : null}
      </Spin>
    </Modal>
  );
}

function ProjectInfoTitle({ project }: { project: WorkProject | null }) {
  return (
    <div className="project-info-title">
      <strong>{project?.name ?? "Work Project"}</strong>
    </div>
  );
}
