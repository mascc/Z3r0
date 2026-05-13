import { Button } from "@douyinfe/semi-ui";
import { ArrowDown, GitBranch, X } from "lucide-react";
import { useMemo, useRef } from "react";
import type { AgentInfo } from "../../shared/api/types";
import type { AgentTranscript, ChatNode, SubagentExecutionItem } from "./playgroundReducer";
import {
  findSubagentTarget,
  type SubagentSelection,
  type SubagentTab,
  type SubagentTarget,
} from "./subagentView";
import { ExecutionSection, SubagentStatusTag, TranscriptContent } from "./Transcript";
import { useAutoFollowScroll } from "./useAutoFollowScroll";

export function SubagentSidePanel({
  nodes,
  tabs,
  agents,
  selection,
  onSelect,
  onClose,
}: {
  nodes: ChatNode[];
  tabs: SubagentTab[];
  agents: AgentInfo[];
  selection: SubagentSelection | null;
  onSelect: (selection: SubagentSelection) => void;
  onClose: () => void;
}) {
  const target = useMemo(
    () => selection ? findSubagentTarget(nodes, selection) : null,
    [nodes, selection],
  );
  const open = Boolean(selection);
  const agentNameByCode = useMemo(
    () => new Map(agents.map((agent) => [agent.code, agent.name])),
    [agents],
  );
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const selectionKey = selection ?? "";
  const { following: followLatest, tailRef, scrollHandlers, scrollToLatest } = useAutoFollowScroll({
    enabled: open,
    containerRef: bodyRef,
    resetKey: selectionKey,
    watch: [target],
  });

  return (
    <aside className={`subagent-side-panel${open ? " subagent-side-panel-open" : ""}`} aria-hidden={!open}>
      <div className="subagent-side-panel-inner">
        <div className="subagent-side-header">
          <div className="subagent-side-heading">
            <GitBranch size={15} />
            <span>Subagents</span>
          </div>
          {tabs.length > 0 ? (
            <div className="subagent-side-tabs" role="tablist" aria-label="Subagent messages">
              {tabs.map((tab) => {
                const active = selection === tab.agentCode;
                return (
                  <button
                    key={tab.agentCode}
                    type="button"
                    className={`subagent-tab${active ? " subagent-tab-active" : ""}`}
                    role="tab"
                    aria-selected={active}
                    onClick={() => onSelect(tab.agentCode)}
                  >
                    <span className="subagent-tab-name" title={tab.agentCode || "subagent"}>
                      {agentNameByCode.get(tab.agentCode) || tab.agentCode || "Subagent"}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : null}
          <Button icon={<X size={14} />} theme="borderless" type="tertiary" onClick={onClose} aria-label="Close subagent panel" />
        </div>
        <div className="subagent-side-body-shell">
          <div ref={bodyRef} className="subagent-side-body" {...scrollHandlers}>
            {target ? <SubagentTargetView target={target} /> : <div className="transcript-empty">Subagent output is no longer available.</div>}
            <div ref={tailRef} className="chat-tail" />
          </div>
          {open && !followLatest ? (
            <Button
              className="subagent-scroll-tail-floating"
              icon={<ArrowDown size={16} />}
              theme="solid"
              type="tertiary"
              onClick={scrollToLatest}
              aria-label="Scroll subagent messages to latest"
            />
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function SubagentTargetView({ target }: { target: SubagentTarget }) {
  return (
    <div className="subagent-transcript-view">
      {target.runs.map((run) => (
        <SubagentRunView key={run.task.runId} run={run} />
      ))}
    </div>
  );
}

function SubagentRunView({ run }: { run: SubagentTarget["runs"][number] }) {
  if (run.transcript) {
    return (
      <div className="subagent-task-view">
        <SubagentTaskMeta item={run.task} />
        <SubagentTranscript transcript={run.transcript} live={run.live} />
      </div>
    );
  }

  const failed = run.task.status === "failed" || run.task.status === "canceled";
  const label = run.task.status === "running" ? "Progress" : failed ? "Error" : "Result";
  const body = run.task.status === "running"
    ? run.task.progress || "Running"
    : run.task.result || run.task.error || "(empty)";

  return (
    <div className="subagent-task-view">
      <SubagentTaskMeta item={run.task} />
      <ExecutionSection label={label} body={body} tone={failed ? "error" : undefined} />
    </div>
  );
}

function SubagentTranscript({ transcript, live }: { transcript: AgentTranscript; live: boolean }) {
  return (
      <TranscriptContent
        transcript={transcript}
        live={live}
      className="transcript-view"
        emptyText="No subagent output yet."
        allowSubagentOpen={false}
      />
  );
}

function SubagentTaskMeta({ item }: { item: SubagentExecutionItem }) {
  return (
    <div className="subagent-task-meta">
      <SubagentStatusTag status={item.status} />
      <span>{item.runId}</span>
      {item.status === "running" && item.progress ? <span>{item.progress}</span> : null}
    </div>
  );
}
