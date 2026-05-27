import { AtSign, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState, type RefObject, type WheelEvent } from "react";
import type { AgentImageInputPart, AgentInfo, AgentInputPart } from "../../shared/api/types";
import { formatDateTime } from "../../shared/lib/date";
import type { AgentTranscript, ChatNode } from "./playgroundReducer";
import { emptyAgentTranscript, isTranscriptEmpty, TranscriptContent } from "./Transcript";
import type { SubagentSelection } from "./subagentView";

type ChatStreamProps = {
  nodes: ChatNode[];
  streaming: boolean;
  agents: AgentInfo[];
  selectedSubagent: SubagentSelection | null;
  tailRef: RefObject<HTMLDivElement | null>;
  onOpenSubagent: (selection: SubagentSelection) => void;
};

export function ChatStream({
  nodes,
  streaming,
  agents,
  selectedSubagent,
  tailRef,
  onOpenSubagent,
}: ChatStreamProps) {
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);
  const [previewScale, setPreviewScale] = useState(1);
  const agentNameByCode = useMemo(
    () => new Map(agents.map((a) => [a.code, a.name])),
    [agents],
  );

  useEffect(() => {
    if (!preview) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPreview(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [preview]);

  const openImagePreview = (image: AgentImageInputPart, index: number) => {
    setPreview({
      src: imageSrc(image),
      alt: `User attachment ${index + 1}`,
    });
    setPreviewScale(1);
  };

  const handlePreviewWheel = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.12 : 0.12;
    setPreviewScale((scale) => Math.min(4, Math.max(0.3, Number((scale + delta).toFixed(2)))));
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
  let lastTargetAgentName = "";

  return (
    <div className="chat-stream">
      {nodes.map((node, index) => {
        if (node.kind === "user") {
          const targetName = resolveAgentName(agentNameByCode, node.targetAgentCode);
          lastTargetAgentName = targetName;
          return (
            <UserBubble
              key={node.id}
              content={node.content}
              displayText={node.displayText}
              targetName={targetName}
              createdAt={node.createdAt}
              onPreviewImage={openImagePreview}
            />
          );
        }
        const isLive = streaming && index === lastIndex;
        if (!isLive && isTranscriptEmpty(node)) return null;
        return (
          <AgentBlock
            key={node.id}
            agentName={node.agentName || lastTargetAgentName}
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
          agentName={resolveAgentName(agentNameByCode, lastNode.targetAgentCode)}
          transcript={emptyAgentTranscript()}
          live
          selectedSubagent={selectedSubagent}
          onOpenSubagent={onOpenSubagent}
        />
      ) : null}
      <div ref={tailRef} className="chat-tail" />
      {preview ? (
        <div
          className="image-preview-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Image preview"
          onClick={() => setPreview(null)}
          onWheel={handlePreviewWheel}
        >
          <button
            type="button"
            className="image-preview-close"
            onClick={() => setPreview(null)}
            aria-label="Close image preview"
            title="Close"
          >
            <X size={20} />
          </button>
          <div className="image-preview-stage">
            <img
              className="image-preview-img"
              src={preview.src}
              alt={preview.alt}
              draggable={false}
              style={{ transform: `scale(${previewScale})` }}
              onClick={(event) => event.stopPropagation()}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MessageTimestamp({ value }: { value: string }) {
  return <time className="message-timestamp" dateTime={value}>{formatDateTime(value)}</time>;
}

function resolveAgentName(agentNameByCode: Map<string, string>, agentCode: string) {
  return agentNameByCode.get(agentCode) ?? agentCode;
}

function UserBubble({
  content,
  displayText,
  targetName,
  createdAt,
  onPreviewImage,
}: {
  content: AgentInputPart[];
  displayText: string;
  targetName: string;
  createdAt: string;
  onPreviewImage: (image: AgentImageInputPart, index: number) => void;
}) {
  const textParts = content.filter((part): part is Extract<AgentInputPart, { type: "text" }> => part.type === "text");
  const imageParts = content.filter((part): part is AgentImageInputPart => part.type === "image");
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
          {textParts.length ? (
            <span className="user-bubble-text">{textParts.map((part) => part.text).join("\n\n")}</span>
          ) : displayText ? (
            <span className="user-bubble-text">{displayText}</span>
          ) : null}
          {imageParts.length ? (
            <div className="user-bubble-images">
              {imageParts.map((part, index) => (
                <button
                  key={`${part.media_type}:${index}:${part.data.length}`}
                  type="button"
                  className="user-bubble-image-button"
                  onClick={() => onPreviewImage(part, index)}
                  aria-label={`Preview attachment ${index + 1}`}
                >
                  <img
                    className="user-bubble-image"
                    src={imageSrc(part)}
                    alt="User attachment"
                  />
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function imageSrc(image: AgentImageInputPart): string {
  return `data:${image.media_type};base64,${image.data}`;
}

function AgentBlock({
  agentName,
  transcript,
  live,
  selectedSubagent,
  onOpenSubagent,
}: {
  agentName: string;
  transcript: AgentTranscript;
  live: boolean;
  selectedSubagent: SubagentSelection | null;
  onOpenSubagent: (selection: SubagentSelection) => void;
}) {
  return (
    <div className="chat-row chat-row-agent">
      <div className="agent-block">
        <div className="agent-header">
          {agentName ? <span>{agentName}</span> : null}
          {live ? <span className="agent-pulse" /> : null}
          {transcript.createdAt ? <MessageTimestamp value={transcript.createdAt} /> : null}
        </div>
        <TranscriptContent
          transcript={transcript}
          live={live}
          pendingEmpty
          selectedSubagent={selectedSubagent}
          onOpenSubagent={onOpenSubagent}
        />
      </div>
    </div>
  );
}
