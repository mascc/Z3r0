import { AtSign, Sparkles } from "lucide-react";
import { useMemo, type RefObject } from "react";
import type { AgentInfo } from "../../shared/api/types";
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
  const agentNameByCode = useMemo(
    () => new Map(agents.map((a) => [a.code, a.name])),
    [agents],
  );

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
          return <UserBubble key={node.id} text={node.text} targetName={targetName} createdAt={node.createdAt} />;
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
    </div>
  );
}

function MessageTimestamp({ value }: { value: string }) {
  return <time className="message-timestamp" dateTime={value}>{formatDateTime(value)}</time>;
}

function resolveAgentName(agentNameByCode: Map<string, string>, agentCode: string) {
  return agentNameByCode.get(agentCode) ?? agentCode;
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
