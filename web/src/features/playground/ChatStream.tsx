import { Tag } from "@douyinfe/semi-ui";
import { AlertOctagon, Bot, Brain, ChevronDown, ChevronRight, Sparkles, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentItem, ChatNode } from "./playgroundReducer";

type ChatStreamProps = {
  nodes: ChatNode[];
  streaming: boolean;
};

export function ChatStream({ nodes, streaming }: ChatStreamProps) {
  const tailRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    tailRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [nodes, streaming]);

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
          — penetration tests, code audits, or threat triage.
        </p>
      </div>
    );
  }

  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];
  return (
    <div className="chat-stream">
      {nodes.map((node, index) => {
        if (node.kind === "user") {
          return <UserBubble key={node.id} text={node.text} />;
        }
        const isLive = streaming && index === lastIndex;
        if (!isLive && node.items.length === 0) return null;
        return <AgentBlock key={node.id} agentName={node.agentName} items={node.items} live={isLive} />;
      })}
      {streaming && lastNode?.kind === "user" ? <AgentBlock key="pending-agent" agentName="" items={[]} live /> : null}
      <div ref={tailRef} className="chat-tail" />
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="chat-row chat-row-user">
      <div className="user-bubble">{text}</div>
    </div>
  );
}

function AgentBlock({
  agentName,
  items,
  live,
}: {
  agentName: string;
  items: AgentItem[];
  live: boolean;
}) {
  const lastItem = items[items.length - 1];
  const isLastItemActive = live && !!lastItem && !isItemComplete(lastItem);
  return (
    <div className="chat-row chat-row-agent">
      <div className="agent-avatar">
        <Bot size={18} />
      </div>
      <div className="agent-block">
        <div className="agent-header">
          <span className="agent-name">{agentName || "Agent"}</span>
          {live ? <span className="agent-pulse" /> : null}
        </div>
        <div className="agent-body">
          {items.length === 0
            ? live
              ? <PendingShimmer />
              : null
            : items.map((item, index) => (
                <AgentItemView
                  key={item.id}
                  item={item}
                  live={live && index === items.length - 1}
                />
              ))}
          {live && !isLastItemActive ? <span className="caret" /> : null}
        </div>
      </div>
    </div>
  );
}

function AgentItemView({ item, live }: { item: AgentItem; live: boolean }) {
  switch (item.kind) {
    case "thinking":
      return <ThinkingBlock text={item.text} active={live && !item.complete} />;
    case "text":
      return <MarkdownText text={item.text} streaming={live && !item.complete} />;
    case "tool":
      return <ToolCard item={item} />;
    case "error":
      return (
        <div className="agent-error">
          <AlertOctagon size={16} />
          <span>{item.message}</span>
        </div>
      );
  }
}

function isItemComplete(item: AgentItem) {
  if (item.kind === "tool") return item.resolved;
  if (item.kind === "error") return true;
  return item.complete;
}

function MarkdownText({ text, streaming }: { text: string; streaming: boolean }) {
  if (!text) {
    return streaming ? <span className="caret" /> : null;
  }
  return (
    <div className="agent-text">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      {streaming ? <span className="caret" /> : null}
    </div>
  );
}

function ThinkingBlock({ text, active }: { text: string; active: boolean }) {
  // default open while streaming, collapsed for history; auto-collapse when the live turn finishes.
  const [open, setOpen] = useState(active);
  const wasActive = useRef(active);
  const bodyRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (wasActive.current && !active) setOpen(false);
    wasActive.current = active;
  }, [active]);

  const cleaned = text.replace(/\n{2,}/g, "\n");

  useEffect(() => {
    if (open && active && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [cleaned, active, open]);

  return (
    <div className={`thinking-block${active ? " thinking-block-active" : ""}`}>
      <button type="button" className="thinking-header" onClick={() => setOpen((next) => !next)}>
        <Brain size={14} />
        <span>{active ? "Thinking…" : "Thought"}</span>
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

function ToolCard({ item }: { item: Extract<AgentItem, { kind: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const status = item.resolved ? (item.isError ? "error" : "ok") : "running";
  const statusLabel = item.resolved ? (item.isError ? "Failed" : "Result") : "Running";
  const statusColor = item.resolved ? (item.isError ? "red" : "green") : "amber";
  const argsPreview = previewObject(item.arguments);
  const outputPreview = previewString(item.output);

  return (
    <div className={`tool-card tool-${status}`}>
      <button type="button" className="tool-head" onClick={() => setOpen((next) => !next)}>
        <span className="tool-icon"><Wrench size={14} /></span>
        <span className="tool-name">{item.name || item.callId}</span>
        <Tag size="small" color={statusColor}>{statusLabel}</Tag>
        <span className="tool-summary">{argsPreview}</span>
        <span className="tool-toggle">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
      </button>
      {open ? (
        <div className="tool-detail">
          <ToolSection label="Arguments" body={formatJson(item.arguments)} />
          <ToolSection
            label="Output"
            body={item.resolved ? (outputPreview || "(empty)") : "Pending…"}
            tone={item.isError ? "error" : undefined}
          />
        </div>
      ) : item.resolved ? (
        <div className="tool-result-preview">{outputPreview || "(empty)"}</div>
      ) : null}
    </div>
  );
}

function ToolSection({ label, body, tone }: { label: string; body: string; tone?: "error" }) {
  return (
    <div className={`tool-section${tone ? ` tool-section-${tone}` : ""}`}>
      <div className="tool-section-label">{label}</div>
      <pre className="tool-section-body">{body}</pre>
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

function previewObject(value: Record<string, unknown>) {
  const entries = Object.entries(value).slice(0, 3);
  if (entries.length === 0) return "";
  return entries
    .map(([key, val]) => `${key}=${previewString(typeof val === "string" ? val : JSON.stringify(val))}`)
    .join("  ");
}

function previewString(value: string, max = 60) {
  const oneLine = value.replace(/\s+/g, " ").trim();
  return oneLine.length > max ? `${oneLine.slice(0, max - 1)}…` : oneLine;
}

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
