import type { AgentContentEvent } from "../../shared/api/types";

export type AgentItem =
  | { kind: "thinking"; id: string; text: string; complete: boolean }
  | { kind: "text"; id: string; text: string; complete: boolean }
  | {
      kind: "tool";
      id: string;
      callId: string;
      name: string;
      arguments: Record<string, unknown>;
      output: string;
      isError: boolean;
      resolved: boolean;
    }
  | { kind: "error"; id: string; message: string };

export type ChatNode =
  | { kind: "user"; id: string; text: string }
  | { kind: "agent"; id: string; agentName: string; items: AgentItem[] };

export type ChatState = {
  nodes: ChatNode[];
  streaming: boolean;
};

export const initialChatState: ChatState = { nodes: [], streaming: false };

function newId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

type AgentNode = Extract<ChatNode, { kind: "agent" }>;

function withCurrentAgent(state: ChatState, mutate: (node: AgentNode) => void): ChatState {
  const nodes = state.nodes.slice();
  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];

  let agent: AgentNode;
  if (lastNode?.kind === "agent") {
    agent = { ...lastNode, items: lastNode.items.slice() };
    nodes[lastIndex] = agent;
  } else {
    agent = { kind: "agent", id: newId(), agentName: "", items: [] };
    nodes.push(agent);
  }
  mutate(agent);
  return { ...state, nodes };
}

function setAgentName(node: AgentNode, name: string) {
  if (name && !node.agentName) {
    node.agentName = name;
  }
}

function upsertStreamingItem(
  node: AgentNode,
  kind: "text" | "thinking",
  itemId: string,
  patch: { delta?: string; text?: string; complete?: boolean },
) {
  const index = node.items.findIndex((item) => item.kind === kind && item.id === itemId);
  if (index === -1) {
    node.items.push({
      kind,
      id: itemId,
      text: patch.text ?? patch.delta ?? "",
      complete: Boolean(patch.complete),
    });
    return;
  }
  const existing = node.items[index] as Extract<AgentItem, { kind: "text" | "thinking" }>;
  node.items[index] = {
    ...existing,
    text: patch.text ?? existing.text + (patch.delta ?? ""),
    complete: patch.complete ?? existing.complete,
  };
}

export function finishChatTurn(state: ChatState): ChatState {
  return { ...state, streaming: false };
}

export function chatReduce(state: ChatState, event: AgentContentEvent): ChatState {
  switch (event.type) {
    case "user_message": {
      const userNode: ChatNode = { kind: "user", id: newId(), text: event.text };
      return { ...state, nodes: [...state.nodes, userNode], streaming: true };
    }

    case "handoff": {
      const agentNode: ChatNode = {
        kind: "agent",
        id: newId(),
        agentName: event.target_agent,
        items: [],
      };
      return { ...state, nodes: [...state.nodes, agentNode] };
    }

    case "thinking_delta":
      return withCurrentAgent(state, (node) => {
        setAgentName(node, event.agent_name);
        upsertStreamingItem(node, "thinking", event.item_id, { delta: event.delta });
      });

    case "thinking_complete":
      return withCurrentAgent(state, (node) => {
        setAgentName(node, event.agent_name);
        upsertStreamingItem(node, "thinking", event.item_id, { text: event.text, complete: true });
      });

    case "text_delta":
      return withCurrentAgent(state, (node) => {
        setAgentName(node, event.agent_name);
        upsertStreamingItem(node, "text", event.item_id, { delta: event.delta });
      });

    case "text_complete":
      return withCurrentAgent(state, (node) => {
        setAgentName(node, event.agent_name);
        upsertStreamingItem(node, "text", event.item_id, { text: event.text, complete: true });
      });

    case "tool_call":
      return withCurrentAgent(state, (node) => {
        setAgentName(node, event.agent_name);
        node.items.push({
          kind: "tool",
          id: newId(),
          callId: event.call_id,
          name: event.name,
          arguments: event.arguments ?? {},
          output: "",
          isError: false,
          resolved: false,
        });
      });

    case "tool_result":
      return withCurrentAgent(state, (node) => {
        setAgentName(node, event.agent_name);
        const index = node.items.findIndex((item) => item.kind === "tool" && item.callId === event.call_id);
        if (index === -1) {
          node.items.push({
            kind: "tool",
            id: newId(),
            callId: event.call_id,
            name: "",
            arguments: {},
            output: event.output,
            isError: event.is_error,
            resolved: true,
          });
          return;
        }
        const existing = node.items[index] as Extract<AgentItem, { kind: "tool" }>;
        node.items[index] = {
          ...existing,
          output: event.output,
          isError: event.is_error,
          resolved: true,
        };
      });

    case "error": {
      const next = withCurrentAgent(state, (node) => {
        setAgentName(node, event.agent_name);
        node.items.push({
          kind: "error",
          id: newId(),
          message: event.message || "agent run failed",
        });
      });
      return finishChatTurn(next);
    }
  }
}

export function chatReplay(events: readonly AgentContentEvent[]): ChatState {
  const replayed = events.reduce<ChatState>(chatReduce, initialChatState);
  return finishChatTurn(replayed);
}
