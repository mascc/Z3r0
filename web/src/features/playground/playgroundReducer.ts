import type {
  AgentContentEvent,
  SubagentTaskEvent,
  TextCompleteEvent,
  ThinkingCompleteEvent,
  ToolCallEvent,
  ToolResultEvent,
} from "../../shared/api/types";

export type ThinkingItem = {
  kind: "thinking";
  id: ThinkingCompleteEvent["item_id"];
  text: ThinkingCompleteEvent["text"];
  complete: boolean;
};

export type TextItem = {
  kind: "text";
  id: TextCompleteEvent["item_id"];
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

export type AgentTranscript = {
  createdAt: AgentContentEvent["created_at"] | "";
  agentName: string;
  thinkingItems: ThinkingItem[];
  executionItems: ExecutionItem[];
  contentItems: TextItem[];
  errorItems: ErrorItem[];
};

export type NestedTranscript = AgentTranscript;

export type ChatNode =
  | { kind: "user"; id: string; createdAt: AgentContentEvent["created_at"]; text: string; targetAgentCode: string }
  | ({ kind: "agent"; id: string } & AgentTranscript);

export type ChatState = {
  nodes: ChatNode[];
  streaming: boolean;
  pendingNested: Record<string, AgentContentEvent[]>;
};

export const initialChatState: ChatState = { nodes: [], streaming: false, pendingNested: {} };

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
  text: string,
  targetAgentCode: string,
  createdAt: AgentContentEvent["created_at"],
): ChatState {
  // idempotent w.r.t. duplicate server frames; repeated user text at a new timestamp remains a new message
  const lastNode = state.nodes[state.nodes.length - 1];
  if (lastNode?.kind === "user" && lastNode.text === text && lastNode.createdAt === createdAt) {
    if (!targetAgentCode || lastNode.targetAgentCode === targetAgentCode) {
      return { ...state, streaming: true };
    }
    const nodes = state.nodes.slice();
    nodes[nodes.length - 1] = { ...lastNode, targetAgentCode };
    return { ...state, nodes, streaming: true };
  }
  return {
    ...state,
    nodes: [...state.nodes, { kind: "user", id: newId(), createdAt, text, targetAgentCode }],
    streaming: true,
  };
}

export function finishChatTurn(state: ChatState): ChatState {
  return { ...state, streaming: false, pendingNested: prunePendingNested(state) };
}

export function chatReduce(state: ChatState, event: AgentContentEvent): ChatState {
  if (event.type === "user_message") {
    return appendUserMessage(state, event.text, event.target_agent_code, event.created_at);
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

// ----------------------------------------------------------- routing

function routeToTopLevel(state: ChatState, event: AgentContentEvent): ChatState {
  const nodes = state.nodes.slice();
  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];

  let agent: AgentNode;
  if (lastNode?.kind === "agent") {
    agent = cloneAgentNode(lastNode);
    if (!agent.createdAt) agent.createdAt = event.created_at;
    nodes[lastIndex] = agent;
  } else {
    agent = createAgentNode(event.created_at);
    nodes.push(agent);
  }

  const finished = applyEventToTranscript(agent, event);
  const nextState = finished ? finishChatTurn({ ...state, nodes }) : { ...state, nodes, streaming: true };
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
    return routeSubagentTaskToToolNow(state, event, nestedCallId);
  }

  // Nested events attach to the top-level tool whose call id matches the backend attribution.
  // Search the full conversation because a subagent can keep running after the user starts a new main-agent turn.
  const nodes = state.nodes.slice();
  for (let i = nodes.length - 1; i >= 0; i -= 1) {
    const node = nodes[i];
    if (node.kind !== "agent") continue;
    const itemIndex = findToolItemIndex(node.executionItems, nestedCallId);
    if (itemIndex === -1) continue;

    const agent = cloneAgentNode(node);
    const tool = { ...(agent.executionItems[itemIndex] as ToolExecutionItem) };
    const nested = tool.nested ? cloneTranscript(tool.nested) : createTranscript(event.created_at);
    if (!nested.createdAt) nested.createdAt = event.created_at;
    applyEventToTranscript(nested, event);
    tool.nested = nested;
    agent.executionItems[itemIndex] = tool;
    nodes[i] = agent;
    return { ...state, nodes };
  }
  return null;
}

function routeSubagentTaskToToolNow(
  state: ChatState,
  event: SubagentTaskEvent,
  nestedCallId: string,
): ChatState | null {
  const nodes = state.nodes.slice();
  for (let i = nodes.length - 1; i >= 0; i -= 1) {
    const node = nodes[i];
    if (node.kind !== "agent") continue;
    const itemIndex = findToolItemIndex(node.executionItems, nestedCallId);
    if (itemIndex === -1) continue;

    const agent = cloneAgentNode(node);
    const tool = { ...(agent.executionItems[itemIndex] as ToolExecutionItem) };
    tool.subagentTask = subagentExecutionItemFromEvent(event);
    agent.executionItems[itemIndex] = tool;
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
  return nodes.some((node) => node.kind === "agent" && findToolItemIndex(node.executionItems, callId) !== -1);
}

// ----------------------------------------------------------- primitives

function applyEventToTranscript(transcript: AgentTranscript, event: AgentContentEvent): boolean {
  // returns true when the event should also flip streaming off (final error)
  switch (event.type) {
    case "user_message":
      return false;

    case "thinking_delta":
      setAgentName(transcript, event.agent_name);
      upsertStreamingItem(transcript.thinkingItems, "thinking", event.item_id, { delta: event.delta });
      return false;

    case "thinking_complete":
      setAgentName(transcript, event.agent_name);
      upsertStreamingItem(transcript.thinkingItems, "thinking", event.item_id, { text: event.text, complete: true });
      return false;

    case "text_delta":
      setAgentName(transcript, event.agent_name);
      upsertStreamingItem(transcript.contentItems, "text", event.item_id, { delta: event.delta });
      return false;

    case "text_complete":
      setAgentName(transcript, event.agent_name);
      upsertStreamingItem(transcript.contentItems, "text", event.item_id, { text: event.text, complete: true });
      return false;

    case "tool_call":
      setAgentName(transcript, event.agent_name);
      upsertToolCall(transcript.executionItems, event.call_id, event.name, event.arguments ?? {});
      return false;

    case "tool_result":
      setAgentName(transcript, event.agent_name);
      upsertToolResult(transcript.executionItems, event.call_id, event.output, event.is_error);
      return false;

    case "subagent_task":
      setAgentName(transcript, event.agent_name);
      upsertSubagentTask(transcript.executionItems, subagentExecutionItemFromEvent(event));
      return false;

    case "error":
      setAgentName(transcript, event.agent_name);
      transcript.errorItems.push({ kind: "error", id: newId(), message: event.message || "agent run failed" });
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
    thinkingItems: [],
    executionItems: [],
    contentItems: [],
    errorItems: [],
  };
}

function cloneAgentNode(node: AgentNode): AgentNode {
  return { ...node, ...cloneTranscript(node) };
}

function cloneTranscript(transcript: AgentTranscript): AgentTranscript {
  return {
    createdAt: transcript.createdAt,
    agentName: transcript.agentName,
    thinkingItems: transcript.thinkingItems.slice(),
    executionItems: transcript.executionItems.slice(),
    contentItems: transcript.contentItems.slice(),
    errorItems: transcript.errorItems.slice(),
  };
}

function setAgentName(transcript: AgentTranscript, name: string) {
  if (name && !transcript.agentName) transcript.agentName = name;
}

function upsertStreamingItem(
  items: StreamingItem[],
  kind: StreamingItem["kind"],
  itemId: string,
  patch: { delta?: string; text?: string; complete?: boolean },
) {
  const index = items.findIndex((item) => item.kind === kind && item.id === itemId);
  if (index === -1) {
    items.push({
      kind,
      id: itemId,
      text: patch.text ?? patch.delta ?? "",
      complete: Boolean(patch.complete),
    } as StreamingItem);
    return;
  }
  const existing = items[index];
  items[index] = {
    ...existing,
    text: patch.text ?? existing.text + (patch.delta ?? ""),
    complete: patch.complete ?? existing.complete,
  };
}

function upsertToolCall(
  items: ExecutionItem[],
  callId: string,
  name: string,
  argumentsValue: Record<string, unknown>,
) {
  const index = findToolItemIndex(items, callId);
  if (index === -1) {
    items.push({
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

  const existing = items[index] as ToolExecutionItem;
  items[index] = { ...existing, name, arguments: argumentsValue };
}

function upsertToolResult(items: ExecutionItem[], callId: string, output: string, isError: boolean) {
  const index = findToolItemIndex(items, callId);
  if (index === -1) {
    items.push({
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

  const existing = items[index] as ToolExecutionItem;
  items[index] = { ...existing, output, isError, resolved: true };
}

function upsertSubagentTask(items: ExecutionItem[], nextItem: SubagentExecutionItem) {
  const index = items.findIndex((item) => item.kind === "subagent" && item.runId === nextItem.runId);
  if (index === -1) {
    items.push(nextItem);
    return;
  }
  items[index] = nextItem;
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

function findToolItemIndex(items: ExecutionItem[], callId: string): number {
  return items.findIndex((item) => item.kind === "tool" && item.callId === callId);
}
