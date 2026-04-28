import { apiRequest } from "./client";
import type {
  CreateAgentSessionResponse,
  DeleteAgentSessionResponse,
  ListAgentEventsResponse,
  ListAgentSessionsResponse,
} from "./types";

const AGENT_SESSIONS_PATH = "/api/agent-sessions";

export function listAgentSessions(limit = 100) {
  return apiRequest<ListAgentSessionsResponse>(`${AGENT_SESSIONS_PATH}?limit=${limit}`);
}

export function createAgentSession() {
  return apiRequest<CreateAgentSessionResponse>(AGENT_SESSIONS_PATH, { method: "POST" });
}

export function listAgentEvents(sessionId: string) {
  return apiRequest<ListAgentEventsResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/events`,
  );
}

export function deleteAgentSession(sessionId: string) {
  return apiRequest<DeleteAgentSessionResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}

export function buildAgentStreamUrl(sessionId: string, token: string) {
  const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${wsScheme}://${window.location.host}${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/stream?token=${encodeURIComponent(token)}`;
}
