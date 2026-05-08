import { Button, Tag } from "@douyinfe/semi-ui";
import {
  AlertOctagon,
  AtSign,
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  GitBranch,
  PanelRightOpen,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import { TouchEvent as ReactTouchEvent, WheelEvent as ReactWheelEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentInfo } from "../../shared/api/types";
import { formatDateTime } from "../../shared/lib/date";
import type {
  AgentTranscript,
  ChatNode,
  ErrorItem,
  ExecutionItem,
  NestedTranscript,
  SubagentExecutionItem,
  TextItem,
  ThinkingItem,
  ToolExecutionItem,
} from "./playgroundReducer";
import { normalizeMarkdownForRender } from "./markdown";
import {
  findSubagentTarget,
  isSelectedSubagent,
  subagentStatusColor,
  subordinateStatusLabel,
  type SubagentSelection,
  type SubagentTab,
  type SubagentTarget,
} from "./subagentView";

type ChatStreamProps = {
  nodes: ChatNode[];
  streaming: boolean;
  agents: AgentInfo[];
  followLatest: boolean;
  selectedSubagent: SubagentSelection | null;
  onOpenSubagent: (selection: SubagentSelection) => void;
  onFollowLatestChange: (following: boolean) => void;
  onScrollToLatestReady: (handler: (() => void) | null) => void;
};

export function ChatStream({
  nodes,
  streaming,
  agents,
  followLatest,
  selectedSubagent,
  onOpenSubagent,
  onFollowLatestChange,
  onScrollToLatestReady,
}: ChatStreamProps) {
  const tailRef = useRef<HTMLDivElement | null>(null);
  const touchStartYRef = useRef<number | null>(null);
  const lastScrollTopRef = useRef(0);
  const agentNameByCode = useMemo(
    () => new Map(agents.map((a) => [a.code, a.name])),
    [agents],
  );

  useEffect(() => {
    const container = findScrollContainer(tailRef.current);
    if (!container) {
      onScrollToLatestReady(null);
      return;
    }

    const syncFollowing = () => {
      const scrollingUp = container.scrollTop < lastScrollTopRef.current - 2;
      lastScrollTopRef.current = container.scrollTop;
      if (scrollingUp) {
        onFollowLatestChange(false);
        return;
      }
      if (isNearScrollTail(container)) {
        onFollowLatestChange(true);
      }
    };

    const scrollToTail = () => {
      onFollowLatestChange(true);
      tailRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    };

    syncFollowing();
    onScrollToLatestReady(scrollToTail);
    container.addEventListener("scroll", syncFollowing, { passive: true });
    return () => {
      container.removeEventListener("scroll", syncFollowing);
      onScrollToLatestReady(null);
    };
  }, [nodes.length, onFollowLatestChange, onScrollToLatestReady]);

  useEffect(() => {
    if (!followLatest) return;
    tailRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [followLatest, nodes, streaming]);

  const pauseFollowLatest = () => {
    if (followLatest) onFollowLatestChange(false);
  };

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (event.deltaY < 0) pauseFollowLatest();
  };

  const handleTouchStart = (event: ReactTouchEvent<HTMLDivElement>) => {
    touchStartYRef.current = event.touches[0]?.clientY ?? null;
  };

  const handleTouchMove = (event: ReactTouchEvent<HTMLDivElement>) => {
    const startY = touchStartYRef.current;
    const currentY = event.touches[0]?.clientY;
    if (startY != null && currentY != null && currentY > startY) {
      pauseFollowLatest();
    }
  };

  if (nodes.length === 0) {
    return (
      <div className="chat-empty">
        <div className="chat-empty-mark">
          <Sparkles size={28} />
        </div>
        <h2>Start a new conversation</h2>
        <p>
          Ask the security operations agent anything
          <br />
          - penetration tests, code audits, or threat triage.
        </p>
      </div>
    );
  }

  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];
  return (
    <div
      className="chat-stream"
      onWheel={handleWheel}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
    >
      {nodes.map((node, index) => {
        if (node.kind === "user") {
          const targetName = agentNameByCode.get(node.targetAgentCode) ?? node.targetAgentCode;
          return <UserBubble key={node.id} text={node.text} targetName={targetName} createdAt={node.createdAt} />;
        }
        const isLive = streaming && index === lastIndex;
        if (!isLive && isTranscriptEmpty(node)) return null;
        return (
          <AgentBlock
            key={node.id}
            transcript={node}
            live={isLive}
            selectedSubagent={selectedSubagent}
            onOpenSubagent={onOpenSubagent}
          />
        );
      })}
      {streaming && lastNode?.kind === "user" ? (
        <AgentBlock
          key="pending-agent"
          transcript={emptyAgentTranscript()}
          live
          selectedSubagent={selectedSubagent}
          onOpenSubagent={onOpenSubagent}
        />
      ) : null}
      <div ref={tailRef} className="chat-tail" />
    </div>
  );
}

export function SubagentSidePanel({
  nodes,
  streaming,
  tabs,
  selection,
  onSelect,
  onClose,
}: {
  nodes: ChatNode[];
  streaming: boolean;
  tabs: SubagentTab[];
  selection: SubagentSelection | null;
  onSelect: (selection: SubagentSelection) => void;
  onClose: () => void;
}) {
  const target = useMemo(
    () => selection ? findSubagentTarget(nodes, streaming, selection) : null,
    [nodes, streaming, selection],
  );
  const open = Boolean(selection);
  const title = target?.kind === "task"
    ? target.item.agentCode || "subagent"
    : target?.task?.agentCode || target?.transcript.agentName || "Subagent";

  return (
    <aside className={`subagent-side-panel${open ? " subagent-side-panel-open" : ""}`} aria-hidden={!open}>
      <div className="subagent-side-panel-inner">
        <div className="subagent-side-header">
          <div className="subagent-side-heading">
            <GitBranch size={15} />
            <span>{tabs.length > 1 ? "Subagents" : title}</span>
          </div>
          {tabs.length > 0 ? (
            <div className="subagent-side-tabs" role="tablist" aria-label="Subagent messages">
              {tabs.map((tab) => {
                const active = selection?.agentCode === tab.agentCode;
                return (
                  <button
                    key={tab.agentCode}
                    type="button"
                    className={`subagent-tab${active ? " subagent-tab-active" : ""}`}
                    role="tab"
                    aria-selected={active}
                    onClick={() => onSelect(tab.selection)}
                  >
                    <span className="subagent-tab-name" title={tab.agentCode || "subagent"}>{tab.agentCode || "subagent"}</span>
                    <SubagentStatusTag status={tab.status} />
                  </button>
                );
              })}
            </div>
          ) : null}
          <Button icon={<X size={14} />} theme="borderless" type="tertiary" onClick={onClose} aria-label="Close subagent panel" />
        </div>
        <div className="subagent-side-body">
          {target ? <SubagentTargetView target={target} /> : <div className="transcript-empty">Subagent output is no longer available.</div>}
        </div>
      </div>
    </aside>
  );
}

function isNearScrollTail(container: HTMLElement) {
  return container.scrollHeight - container.scrollTop - container.clientHeight < 72;
}

function findScrollContainer(element: HTMLElement | null) {
  let current = element?.parentElement ?? null;
  while (current) {
    const overflowY = window.getComputedStyle(current).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") {
      return current;
    }
    current = current.parentElement;
  }
  return null;
}

function MessageTimestamp({ value }: { value: string }) {
  return <time className="message-timestamp" dateTime={value}>{formatDateTime(value)}</time>;
}

function UserBubble({ text, targetName, createdAt }: { text: string; targetName: string; createdAt: string }) {
  return (
    <div className="chat-row chat-row-user">
      <div className="chat-message chat-message-user">
        <MessageTimestamp value={createdAt} />
        <div className="user-bubble">
          {targetName ? (
            <span className="user-bubble-mention">
              <AtSign size={11} />
              <span>{targetName}</span>
            </span>
          ) : null}
          <span className="user-bubble-text">{text}</span>
        </div>
      </div>
    </div>
  );
}

function AgentBlock({
  transcript,
  live,
  selectedSubagent,
  onOpenSubagent,
}: {
  transcript: AgentTranscript;
  live: boolean;
  selectedSubagent: SubagentSelection | null;
  onOpenSubagent: (selection: SubagentSelection) => void;
}) {
  const activeContent = live && hasActiveContent(transcript.contentItems);
  const activeThinkingId = live ? activeThinkingItemId(transcript.thinkingItems) : "";
  const thinkingActive = Boolean(activeThinkingId);
  const hasContent = transcript.contentItems.length > 0;
  const isEmpty = isTranscriptEmpty(transcript);

  return (
    <div className="chat-row chat-row-agent">
      <div className="agent-avatar">
        <Bot size={18} />
      </div>
      <div className="agent-block">
        <div className="agent-header">
          <span className="agent-name">{transcript.agentName || "Agent"}</span>
          {live ? <span className="agent-pulse" /> : null}
          {transcript.createdAt ? <MessageTimestamp value={transcript.createdAt} /> : null}
        </div>
        <div className="agent-body">
          {isEmpty && live ? <PendingShimmer /> : null}
          <ThinkingBlock items={transcript.thinkingItems} active={thinkingActive} />
          <ExecutionDock
            items={transcript.executionItems}
            live={live}
            selectedSubagent={selectedSubagent}
            onOpenSubagent={onOpenSubagent}
          />
          {hasContent ? <ContentStack items={transcript.contentItems} live={live} /> : null}
          {transcript.errorItems.map((item) => <ErrorNotice key={item.id} item={item} />)}
          {live && !isEmpty && !activeContent ? <span className="caret" /> : null}
        </div>
      </div>
    </div>
  );
}

function ContentStack({ items, live }: { items: TextItem[]; live: boolean }) {
  const activeId = live ? activeTextItemId(items) : "";
  return (
    <div className="agent-content-stack">
      {items.map((item) => (
        <MarkdownText key={item.id} text={item.text} streaming={item.id === activeId && !item.complete} />
      ))}
    </div>
  );
}

function MarkdownText({ text, streaming }: { text: string; streaming: boolean }) {
  const markdown = useMemo(() => normalizeMarkdownForRender(text, streaming), [streaming, text]);
  if (!text) {
    return streaming ? <span className="caret" /> : null;
  }
  return (
    <div className="agent-text">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      {streaming ? <span className="caret" /> : null}
    </div>
  );
}

function ThinkingBlock({ items, active }: { items: ThinkingItem[]; active: boolean }) {
  // default open while streaming, collapsed for history; auto-collapse when the live turn finishes.
  const [open, setOpen] = useState(active);
  const wasActive = useRef(active);
  const bodyRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (wasActive.current && !active) setOpen(false);
    wasActive.current = active;
  }, [active]);

  const cleaned = useMemo(
    () => items.map((item) => item.text.trim()).filter(Boolean).join("\n\n").replace(/\n{3,}/g, "\n\n"),
    [items],
  );

  if (items.length === 0) return null;

  useEffect(() => {
    if (open && active && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [cleaned, active, open]);

  return (
    <div className={`thinking-block${active ? " thinking-block-active" : ""}`}>
      <button type="button" className="thinking-header" onClick={() => setOpen((next) => !next)}>
        <Brain size={14} />
        <span>{active ? "Thinking..." : "Thought"}</span>
        {items.length > 1 ? <span className="thinking-count">{items.length}</span> : null}
        <span className="thinking-toggle">
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      </button>
      {open ? (
        <div className="thinking-body">
          <div className="thinking-fade thinking-fade-top" />
          <pre ref={bodyRef} className="thinking-text">{cleaned || (active ? " " : "(empty)")}</pre>
          <div className="thinking-fade thinking-fade-bottom" />
        </div>
      ) : null}
    </div>
  );
}

function ExecutionDock({
  items,
  live,
  selectedSubagent,
  onOpenSubagent,
  allowSubagentOpen = true,
}: {
  items: ExecutionItem[];
  live: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
  allowSubagentOpen?: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;

  const runningCount = items.filter(isExecutionRunning).length;
  const failedCount = items.filter(isExecutionFailed).length;
  const statusLabel = failedCount > 0 ? `${failedCount} failed` : runningCount > 0 ? `${runningCount} running` : "Complete";
  const statusTone = failedCount > 0 ? "red" : runningCount > 0 ? "amber" : "green";

  return (
    <div className={`execution-dock${open ? " execution-dock-open" : ""}${live && runningCount > 0 ? " execution-dock-live" : ""}`}>
      <button type="button" className="execution-dock-header" onClick={() => setOpen((next) => !next)}>
        <Wrench size={14} />
        <span className="execution-dock-title">Execution</span>
        <span className="execution-dock-count">{items.length}</span>
        <Tag size="small" color={statusTone}>{statusLabel}</Tag>
        <span className="execution-dock-toggle">
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      </button>
      {open ? (
        <div className="execution-dock-body">
          {items.map((item) => (
            item.kind === "tool"
              ? (
                <ToolExecutionRow
                  key={item.id}
                  item={item}
                  live={live}
                  selectedSubagent={allowSubagentOpen ? selectedSubagent : null}
                  onOpenSubagent={allowSubagentOpen ? onOpenSubagent : undefined}
                  allowSubagentOpen={allowSubagentOpen}
                />
              ) : (
                <SubagentExecutionRow
                  key={item.id}
                  item={item}
                  selected={allowSubagentOpen && isSelectedSubagent(selectedSubagent, { kind: "agent", agentCode: item.agentCode })}
                  onOpenSubagent={allowSubagentOpen ? onOpenSubagent : undefined}
                />
              )
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ToolExecutionRow({
  item,
  live,
  selectedSubagent,
  onOpenSubagent,
  allowSubagentOpen,
}: {
  item: ToolExecutionItem;
  live: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
  allowSubagentOpen: boolean;
}) {
  const [open, setOpen] = useState(false);
  const nestedActive = !!item.nested && transcriptHasRunningExecution(item.nested);
  const status = toolExecutionStatus(item);
  const displayName = item.name || item.callId || "tool";
  const detailOpen = open;

  return (
    <div className={`execution-row execution-row-${status.tone}`}>
      <button type="button" className="execution-row-head" onClick={() => setOpen((next) => !next)}>
        <span className="execution-row-icon"><Wrench size={13} /></span>
        <span className="execution-row-name" title={displayName}>{displayName}</span>
        <Tag size="small" color={status.color}>{status.label}</Tag>
        <span className="execution-row-spacer" />
        <span className="execution-row-toggle">{detailOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
      </button>
      {detailOpen ? (
        <div className="execution-row-detail">
          <ExecutionSection label="Arguments" body={formatJson(item.arguments)} />
          {allowSubagentOpen && (item.nested || item.subagentTask) ? (
            <NestedTranscriptPanel
              nested={item.nested ?? emptyAgentTranscript()}
              task={item.subagentTask}
              live={live && (nestedActive || item.subagentTask?.status === "running")}
              selected={item.subagentTask ? isSelectedSubagent(selectedSubagent, { kind: "agent", agentCode: item.subagentTask.agentCode }) : false}
              onOpenSubagent={onOpenSubagent}
            />
          ) : null}
          <ExecutionSection
            label="Output"
            body={item.resolved ? (item.output || "(empty)") : "Pending..."}
            tone={item.isError ? "error" : undefined}
          />
        </div>
      ) : null}
    </div>
  );
}

function SubagentExecutionRow({
  item,
  selected,
  onOpenSubagent,
}: {
  item: SubagentExecutionItem;
  selected: boolean;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  return (
    <div className={`execution-row execution-row-subagent execution-row-subagent-${item.status}${selected ? " execution-row-selected" : ""}`}>
      <div className="execution-row-head execution-row-head-static">
        <span className="execution-row-icon"><GitBranch size={13} /></span>
        <span className="execution-row-name" title={item.agentCode || "subagent"}>{item.agentCode || "subagent"}</span>
        <SubagentStatusTag status={item.status} />
        <span className="execution-row-spacer" />
      </div>
      {onOpenSubagent ? (
        <Button
          className="execution-row-expand"
          icon={<PanelRightOpen size={13} />}
          size="small"
          theme="borderless"
          type="tertiary"
          onClick={() => onOpenSubagent({ kind: "agent", agentCode: item.agentCode })}
        >
          Open
        </Button>
      ) : null}
    </div>
  );
}

function NestedTranscriptPanel({
  nested,
  task,
  live,
  selected,
  onOpenSubagent,
}: {
  nested: NestedTranscript;
  task?: SubagentExecutionItem;
  live: boolean;
  selected: boolean;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  const itemCount = transcriptItemCount(nested);
  if (itemCount === 0 && !task) return null;

  return (
    <div className={`nested-panel${live ? " nested-panel-live" : ""}${selected ? " nested-panel-selected" : ""}`}>
      <div className="nested-panel-head nested-panel-head-static">
        <GitBranch size={13} />
        <span>Subagent{task?.agentCode ? ` - ${task.agentCode}` : nested.agentName ? ` - ${nested.agentName}` : ""}</span>
        {task ? <SubagentStatusTag status={task.status} /> : null}
        <span className="nested-panel-count">{itemCount}</span>
      </div>
      <Button
        className="nested-panel-expand"
        icon={<PanelRightOpen size={13} />}
        size="small"
        theme="borderless"
        type="tertiary"
        disabled={!task}
        onClick={() => task && onOpenSubagent?.({ kind: "agent", agentCode: task.agentCode })}
      >
        Open
      </Button>
    </div>
  );
}

function TranscriptView({ transcript, live, expanded = false }: { transcript: AgentTranscript; live: boolean; expanded?: boolean }) {
  const activeThinkingId = live ? activeThinkingItemId(transcript.thinkingItems) : "";
  const thinkingActive = Boolean(activeThinkingId);
  return (
    <div className={expanded ? "transcript-view transcript-view-expanded" : "transcript-view"}>
      <ThinkingBlock items={transcript.thinkingItems} active={thinkingActive} />
      <ExecutionDock items={transcript.executionItems} live={live} allowSubagentOpen={false} />
      {transcript.contentItems.length > 0 ? <ContentStack items={transcript.contentItems} live={live} /> : null}
      {transcript.errorItems.map((item) => <ErrorNotice key={item.id} item={item} />)}
      {isTranscriptEmpty(transcript) ? <div className="transcript-empty">No subagent output yet.</div> : null}
    </div>
  );
}

function SubagentTargetView({ target }: { target: SubagentTarget }) {
  if (target.kind === "transcript") {
    return (
      <div className="subagent-transcript-view">
        {target.task ? <SubagentTaskMeta item={target.task} /> : null}
        <TranscriptView transcript={target.transcript} live={target.live} expanded />
      </div>
    );
  }

  const failed = target.item.status === "failed" || target.item.status === "canceled";
  const label = target.item.status === "running" ? "Progress" : failed ? "Error" : "Result";
  const body = target.item.status === "running"
    ? target.item.progress || "Running"
    : target.item.result || target.item.error || "(empty)";

  return (
    <div className="subagent-task-view">
      <SubagentTaskMeta item={target.item} />
      <ExecutionSection label={label} body={body} tone={failed ? "error" : undefined} expanded />
    </div>
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

function SubagentStatusTag({ status }: { status: SubagentExecutionItem["status"] }) {
  return <Tag size="small" color={subagentStatusColor(status)}>{subordinateStatusLabel(status)}</Tag>;
}

function ExecutionSection({ label, body, tone, expanded = false }: { label: string; body: string; tone?: "error"; expanded?: boolean }) {
  return (
    <div className={`execution-section${tone ? ` execution-section-${tone}` : ""}${expanded ? " execution-section-expanded" : ""}`}>
      <div className="execution-section-label">{label}</div>
      <pre className="execution-section-body">{body}</pre>
    </div>
  );
}

function ErrorNotice({ item }: { item: ErrorItem }) {
  return (
    <div className="agent-error">
      <AlertOctagon size={16} />
      <span>{item.message}</span>
    </div>
  );
}

function PendingShimmer() {
  return (
    <div className="agent-pending">
      <span /><span /><span />
    </div>
  );
}

function isTranscriptEmpty(transcript: AgentTranscript) {
  return transcript.thinkingItems.length === 0 &&
    transcript.executionItems.length === 0 &&
    transcript.contentItems.length === 0 &&
    transcript.errorItems.length === 0;
}

function emptyAgentTranscript(): AgentTranscript {
  return {
    createdAt: "",
    agentName: "",
    thinkingItems: [],
    executionItems: [],
    contentItems: [],
    errorItems: [],
  };
}

function activeThinkingItemId(items: ThinkingItem[]) {
  return [...items].reverse().find((item) => !item.complete)?.id ?? "";
}

function activeTextItemId(items: TextItem[]) {
  return [...items].reverse().find((item) => !item.complete)?.id ?? "";
}

function hasActiveContent(items: TextItem[]) {
  return items.some((item) => !item.complete);
}

function isExecutionRunning(item: ExecutionItem) {
  if (item.kind === "tool") {
    return !item.resolved || item.subagentTask?.status === "running" || Boolean(item.nested && transcriptHasRunningExecution(item.nested));
  }
  return item.status === "running";
}

function isExecutionFailed(item: ExecutionItem) {
  if (item.kind === "tool") {
    return (item.resolved && item.isError) || item.subagentTask?.status === "failed" || item.subagentTask?.status === "canceled";
  }
  return item.status === "failed" || item.status === "canceled";
}

function transcriptHasRunningExecution(transcript: AgentTranscript): boolean {
  return transcript.executionItems.some(isExecutionRunning);
}

function toolExecutionStatus(item: ToolExecutionItem): { label: string; color: "red" | "green" | "amber"; tone: "error" | "ok" | "running" } {
  if (item.resolved && item.isError) return { label: "Failed", color: "red", tone: "error" };
  if (item.subagentTask?.status === "failed" || item.subagentTask?.status === "canceled") {
    return { label: subordinateStatusLabel(item.subagentTask.status), color: "red", tone: "error" };
  }
  if (!item.resolved || item.subagentTask?.status === "running") return { label: "Running", color: "amber", tone: "running" };
  return { label: "Done", color: "green", tone: "ok" };
}

function transcriptItemCount(transcript: AgentTranscript) {
  return transcript.thinkingItems.length + transcript.executionItems.length + transcript.contentItems.length + transcript.errorItems.length;
}

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
