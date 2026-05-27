import type {
  AgentContentEvent,
  AgentInputPart,
  AgentStreamEvent,
  SubagentTaskEvent,
  TextCompleteEvent,
  ThinkingCompleteEvent,
  ToolCallEvent,
  ToolResultEvent,
} from "../../shared/api/types";

export type ThinkingItem = {
  kind: "thinking";
  id: ThinkingCompleteEvent["segment_id"];
  text: ThinkingCompleteEvent["text"];
  complete: boolean;
};

export type TextItem = {
  kind: "text";
  id: TextCompleteEvent["segment_id"];
  text: TextCompleteEvent["text"];
  complete: boolean;
};

export type ToolExecutionItem = {
  kind: "tool";
  id: string;
  callId: ToolCallEvent["call_id"];
  name: ToolCallEvent["name"];
  arguments: NonNullable<ToolCallEvent["arguments"]>;
  output: ToolResultEvent["output"];
  isError: ToolResultEvent["is_error"];
  resolved: boolean;
  nested?: NestedTranscript;
  subagentTask?: SubagentExecutionItem;
};

export type SubagentExecutionItem = {
  kind: "subagent";
  id: SubagentTaskEvent["run_id"];
  createdAt: SubagentTaskEvent["created_at"];
  runId: SubagentTaskEvent["run_id"];
  parentAgentCode: SubagentTaskEvent["parent_agent_code"];
  parentAgentInstanceId: SubagentTaskEvent["parent_agent_instance_id"];
  agentCode: SubagentTaskEvent["agent_code"];
  nestedCallId: SubagentTaskEvent["nested_call_id"];
  status: SubagentTaskEvent["status"];
  result: SubagentTaskEvent["result"];
  error: SubagentTaskEvent["error"];
  progress: SubagentTaskEvent["progress"];
};

export type ErrorItem = { kind: "error"; id: string; message: string };
export type ExecutionItem = ToolExecutionItem | SubagentExecutionItem;
export type TranscriptBlock = ThinkingItem | TextItem | ExecutionItem | ErrorItem;

export type AgentTranscript = {
  createdAt: AgentContentEvent["created_at"] | "";
  agentName: string;
  blocks: TranscriptBlock[];
};

export type NestedTranscript = AgentTranscript;

export type ChatNode =
  | {
      kind: "user";
      id: string;
      createdAt: AgentContentEvent["created_at"];
      content: AgentInputPart[];
      displayText: string;
      targetAgentCode: string;
    }
  | ({ kind: "agent"; id: string } & AgentTranscript);

export type ChatState = {
  nodes: ChatNode[];
  streaming: boolean;
  pendingNested: Record<string, AgentContentEvent[]>;
  liveFrom: number | null;
};

export const initialChatState: ChatState = { nodes: [], streaming: false, pendingNested: {}, liveFrom: null };

function newId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

type AgentNode = Extract<ChatNode, { kind: "agent" }>;
type StreamingItem = ThinkingItem | TextItem;

export function appendUserMessage(
  state: ChatState,
  content: AgentInputPart[],
  displayText: string,
  targetAgentCode: string,
  createdAt: AgentContentEvent["created_at"],
): ChatState {
  const signature = contentSignature(content);
  const lastNode = state.nodes[state.nodes.length - 1];
  if (state.streaming) {
    const existingIndex = findLiveUserMessageIndex(state.nodes, signature, targetAgentCode);
    if (existingIndex !== -1) {
      const existing = state.nodes[existingIndex];
      if (existing.kind !== "user" || !targetAgentCode || existing.targetAgentCode === targetAgentCode) {
        return { ...state, streaming: true, liveFrom: state.liveFrom ?? state.nodes.length };
      }
      const nodes = state.nodes.slice();
      nodes[existingIndex] = { ...existing, targetAgentCode };
      return { ...state, nodes, streaming: true, liveFrom: state.liveFrom ?? nodes.length };
    }
  }
  if (
    lastNode?.kind === "user"
    && contentSignature(lastNode.content) === signature
    && (state.streaming || lastNode.createdAt === createdAt)
  ) {
    const liveFrom = state.nodes.length;
    if (!targetAgentCode || lastNode.targetAgentCode === targetAgentCode) {
      return { ...state, streaming: true, liveFrom };
    }
    const nodes = state.nodes.slice();
    nodes[nodes.length - 1] = { ...lastNode, targetAgentCode };
    return { ...state, nodes, streaming: true, liveFrom };
  }
  const nodes = [...state.nodes, {
    kind: "user" as const,
    id: newId(),
    createdAt,
    content,
    displayText,
    targetAgentCode,
  }];
  return {
    ...state,
    nodes,
    streaming: true,
    liveFrom: nodes.length,
  };
}

function findLiveUserMessageIndex(nodes: ChatNode[], signature: string, targetAgentCode: string): number {
  for (let index = nodes.length - 1; index >= 0; index -= 1) {
    const node = nodes[index];
    if (node.kind !== "user") continue;
    if (contentSignature(node.content) !== signature) return -1;
    if (!targetAgentCode || !node.targetAgentCode || node.targetAgentCode === targetAgentCode) {
      return index;
    }
    return -1;
  }
  return -1;
}

export function finishChatTurn(state: ChatState): ChatState {
  return { ...state, streaming: false, liveFrom: null, pendingNested: prunePendingNested(state) };
}

export function disconnectChatTurn(state: ChatState): ChatState {
  if (!state.streaming) return state;
  const nodes = state.liveFrom === null ? state.nodes : state.nodes.slice(0, state.liveFrom);
  return { ...state, nodes, streaming: false, liveFrom: null, pendingNested: prunePendingNested({ ...state, nodes }) };
}

export function chatReduce(state: ChatState, event: AgentContentEvent): ChatState {
  return applyContentEvent(state, event);
}

export function streamReduce(state: ChatState, event: AgentStreamEvent): ChatState {
  if (event.type === "done") return finishChatTurn(state);
  if (event.type === "run_state") {
    return event.running ? { ...state, streaming: true, liveFrom: state.liveFrom ?? state.nodes.length } : finishChatTurn(state);
  }
  return applyContentEvent(state, event);
}

function applyContentEvent(state: ChatState, event: AgentContentEvent): ChatState {
  if (event.type === "user_message") {
    return appendUserMessage(state, event.content, event.display_text, event.target_agent_code, event.created_at);
  }
  if (event.type === "turn_boundary") {
    return event.nested_call_id ? state : finishChatTurn(state);
  }

  const nestedCallId = "nested_call_id" in event ? event.nested_call_id : "";
  if (nestedCallId) {
    return routeToNested(state, event, nestedCallId);
  }
  return routeToTopLevel(state, event);
}

export function chatReplay(events: readonly AgentContentEvent[]): ChatState {
  const replayed = events.reduce<ChatState>(chatReduce, initialChatState);
  return finishChatTurn(replayed);
}

function routeToTopLevel(state: ChatState, event: AgentContentEvent): ChatState {
  const nodes = state.nodes.slice();
  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];

  let agent: AgentNode;
  // Notification turns (for example, parent-agent follow-up after a subagent
  // finishes) have no visible user message, so liveFrom can point after the
  // current tail. In that case the first live agent event must start a new node.
  if (
    lastNode?.kind === "agent"
    && state.streaming
    && state.liveFrom !== null
    && lastIndex >= state.liveFrom
  ) {
    agent = cloneAgentNode(lastNode);
    if (!agent.createdAt) agent.createdAt = event.created_at;
    nodes[lastIndex] = agent;
  } else {
    agent = createAgentNode(event.created_at);
    nodes.push(agent);
  }

  const finished = applyEventToTranscript(agent, event);
  const liveFrom = state.liveFrom ?? nodes.length - 1;
  const nextState = finished
    ? finishChatTurn({ ...state, nodes, liveFrom })
    : { ...state, nodes, streaming: true, liveFrom };
  if (event.type === "tool_call" || event.type === "tool_result") {
    return drainPendingNested(nextState, event.call_id);
  }
  if (event.type === "error") return clearPendingNested(nextState);
  return nextState;
}

function routeToNested(state: ChatState, event: AgentContentEvent, nestedCallId: string): ChatState {
  const routed = routeToNestedNow(state, event, nestedCallId);
  if (routed) return routed;

  const queued = state.pendingNested[nestedCallId] ?? [];
  return {
    ...state,
    pendingNested: {
      ...state.pendingNested,
      [nestedCallId]: [...queued, event],
    },
  };
}

function routeToNestedNow(
  state: ChatState,
  event: AgentContentEvent,
  nestedCallId: string,
): ChatState | null {
  if (event.type === "subagent_task") {
    return updateNestedTool(state, nestedCallId, (tool) => {
      tool.subagentTask = subagentExecutionItemFromEvent(event);
    });
  }

  return updateNestedTool(state, nestedCallId, (tool) => {
    const nested = tool.nested ? cloneTranscript(tool.nested) : createTranscript(event.created_at);
    if (!nested.createdAt) nested.createdAt = event.created_at;
    applyEventToTranscript(nested, event);
    tool.nested = nested;
  });
}

function updateNestedTool(
  state: ChatState,
  callId: string,
  update: (tool: ToolExecutionItem) => void,
): ChatState | null {
  const nodes = state.nodes.slice();
  for (let i = nodes.length - 1; i >= 0; i -= 1) {
    const node = nodes[i];
    if (node.kind !== "agent") continue;
    const blockIndex = findToolBlockIndex(node.blocks, callId);
    if (blockIndex === -1) continue;

    const agent = cloneAgentNode(node);
    const tool = { ...(agent.blocks[blockIndex] as ToolExecutionItem) };
    update(tool);
    agent.blocks[blockIndex] = tool;
    nodes[i] = agent;
    return { ...state, nodes };
  }
  return null;
}

function drainPendingNested(state: ChatState, callId: string): ChatState {
  const pending = state.pendingNested[callId];
  if (!pending?.length) return state;

  const remaining: AgentContentEvent[] = [];
  let nextState = state;
  for (const event of pending) {
    const routed = routeToNestedNow(nextState, event, callId);
    if (routed) {
      nextState = routed;
    } else {
      remaining.push(event);
    }
  }

  const pendingNested = { ...nextState.pendingNested };
  if (remaining.length) {
    pendingNested[callId] = remaining;
  } else {
    delete pendingNested[callId];
  }
  return { ...nextState, pendingNested };
}

function clearPendingNested(state: ChatState): ChatState {
  return Object.keys(state.pendingNested).length ? { ...state, pendingNested: {} } : state;
}

function prunePendingNested(state: ChatState): ChatState["pendingNested"] {
  if (!Object.keys(state.pendingNested).length) return state.pendingNested;
  const pendingNested: ChatState["pendingNested"] = {};
  for (const [callId, events] of Object.entries(state.pendingNested)) {
    if (!hasToolCall(state.nodes, callId)) {
      pendingNested[callId] = events;
    }
  }
  return pendingNested;
}

function hasToolCall(nodes: ChatNode[], callId: string): boolean {
  return nodes.some((node) => node.kind === "agent" && findToolBlockIndex(node.blocks, callId) !== -1);
}

function applyEventToTranscript(transcript: AgentTranscript, event: AgentContentEvent): boolean {
  switch (event.type) {
    case "user_message":
    case "turn_boundary":
      return false;

    case "thinking_delta":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "thinking", event.segment_id, { delta: event.delta });
      return false;

    case "thinking_complete":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "thinking", event.segment_id, { text: event.text, complete: true });
      return false;

    case "text_delta":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "text", event.segment_id, { delta: event.delta });
      return false;

    case "text_complete":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "text", event.segment_id, { text: event.text, complete: true });
      return false;

    case "tool_call":
      setAgentName(transcript, event.agent_name);
      upsertToolCall(transcript.blocks, event.call_id, event.name, event.arguments ?? {});
      return false;

    case "tool_result":
      setAgentName(transcript, event.agent_name);
      upsertToolResult(transcript.blocks, event.call_id, event.output, event.is_error);
      return false;

    case "subagent_task":
      setAgentName(transcript, event.agent_name);
      upsertSubagentTask(transcript.blocks, subagentExecutionItemFromEvent(event));
      return false;

    case "error":
      setAgentName(transcript, event.agent_name);
      transcript.blocks.push({ kind: "error", id: newId(), message: event.message || "agent run failed" });
      return true;
  }
}

function createAgentNode(createdAt: AgentContentEvent["created_at"]): AgentNode {
  return { kind: "agent", id: newId(), ...createTranscript(createdAt) };
}

function createTranscript(createdAt: AgentContentEvent["created_at"] | "" = ""): AgentTranscript {
  return {
    createdAt,
    agentName: "",
    blocks: [],
  };
}

function cloneAgentNode(node: AgentNode): AgentNode {
  return { ...node, ...cloneTranscript(node) };
}

function cloneTranscript(transcript: AgentTranscript): AgentTranscript {
  return {
    createdAt: transcript.createdAt,
    agentName: transcript.agentName,
    blocks: transcript.blocks.slice(),
  };
}

function setAgentName(transcript: AgentTranscript, name: string) {
  if (name && !transcript.agentName) transcript.agentName = name;
}

function upsertStreamingBlock(
  blocks: TranscriptBlock[],
  kind: StreamingItem["kind"],
  blockId: string,
  patch: { delta?: string; text?: string; complete?: boolean },
) {
  const index = blocks.findIndex((block) => block.kind === kind && block.id === blockId);
  if (index === -1) {
    const text = patch.text ?? patch.delta ?? "";
    if (patch.complete && text && blocks.some((block) => (
      block.kind === kind
      && block.complete
      && block.text === text
    ))) {
      return;
    }
    blocks.push({
      kind,
      id: blockId,
      text,
      complete: Boolean(patch.complete),
    } as StreamingItem);
    return;
  }
  const existing = blocks[index] as StreamingItem;
  blocks[index] = {
    ...existing,
    text: patch.text ?? existing.text + (patch.delta ?? ""),
    complete: patch.complete ?? existing.complete,
  };
}

function upsertToolCall(
  blocks: TranscriptBlock[],
  callId: string,
  name: string,
  argumentsValue: Record<string, unknown>,
) {
  const index = findToolBlockIndex(blocks, callId);
  if (index === -1) {
    blocks.push({
      kind: "tool",
      id: callId || newId(),
      callId,
      name,
      arguments: argumentsValue,
      output: "",
      isError: false,
      resolved: false,
    });
    return;
  }

  const existing = blocks[index] as ToolExecutionItem;
  blocks[index] = { ...existing, name, arguments: argumentsValue };
}

function upsertToolResult(blocks: TranscriptBlock[], callId: string, output: string, isError: boolean) {
  const index = findToolBlockIndex(blocks, callId);
  if (index === -1) {
    blocks.push({
      kind: "tool",
      id: callId || newId(),
      callId,
      name: "",
      arguments: {},
      output,
      isError,
      resolved: true,
    });
    return;
  }

  const existing = blocks[index] as ToolExecutionItem;
  blocks[index] = { ...existing, output, isError, resolved: true };
}

function upsertSubagentTask(blocks: TranscriptBlock[], nextItem: SubagentExecutionItem) {
  const index = blocks.findIndex((block) => block.kind === "subagent" && block.runId === nextItem.runId);
  if (index === -1) {
    blocks.push(nextItem);
    return;
  }
  blocks[index] = nextItem;
}

function subagentExecutionItemFromEvent(event: SubagentTaskEvent): SubagentExecutionItem {
  return {
    kind: "subagent",
    id: event.run_id,
    createdAt: event.created_at,
    runId: event.run_id,
    parentAgentCode: event.parent_agent_code,
    parentAgentInstanceId: event.parent_agent_instance_id,
    agentCode: event.agent_code,
    nestedCallId: event.nested_call_id,
    status: event.status,
    result: event.result,
    error: event.error,
    progress: event.progress,
  };
}

function findToolBlockIndex(blocks: TranscriptBlock[], callId: string): number {
  return blocks.findIndex((block) => block.kind === "tool" && block.callId === callId);
}

function contentSignature(content: AgentInputPart[]): string {
  return content.map((part) => {
    if (part.type === "text") return `text:${part.text}`;
    return `image:${part.media_type}:${part.data.length}:${part.data.slice(0, 64)}`;
  }).join("\n");
}
