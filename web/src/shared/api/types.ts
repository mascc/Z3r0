import type { components, paths } from "./generated/schema";

type JsonRequestBody<Operation> = Operation extends {
  requestBody: { content: { "application/json": infer Body } };
}
  ? Body
  : never;

type JsonResponse<Operation> = Operation extends {
  responses: { 200: { content: { "application/json": infer Response } } };
}
  ? Response
  : never;

type QueryParameters<Operation> = Operation extends { parameters: { query?: infer Query } } ? Query : never;
type PathParameters<Operation> = Operation extends { parameters: { path?: infer Params } } ? Params : never;

export type CommonResponsePayload = components["schemas"]["CommonResponse"];

export type LoginRequest = JsonRequestBody<paths["/api/system-users/login"]["post"]>;
export type LoginResponse = JsonResponse<paths["/api/system-users/login"]["post"]>;

export type QuerySystemUsersParams = QueryParameters<paths["/api/system-users"]["get"]>;
export type QuerySystemUsersResponse = JsonResponse<paths["/api/system-users"]["get"]>;
export type QuerySystemUsersData = NonNullable<QuerySystemUsersResponse["data"]>;
export type SystemUser = QuerySystemUsersData["items"][number];
export type SystemUserRole = SystemUser["role"];

export type CreateSystemUserRequest = JsonRequestBody<paths["/api/system-users"]["post"]>;
export type CreateSystemUserResponse = JsonResponse<paths["/api/system-users"]["post"]>;

export type SystemUserPathParams = PathParameters<paths["/api/system-users/{id}"]["patch"]>;
export type UpdateSystemUserRequest = JsonRequestBody<paths["/api/system-users/{id}"]["patch"]>;
export type UpdateSystemUserResponse = JsonResponse<paths["/api/system-users/{id}"]["patch"]>;
export type DeleteSystemUserResponse = JsonResponse<paths["/api/system-users/{id}"]["delete"]>;

export type QuerySandboxImagesParams = QueryParameters<paths["/api/sandbox-images"]["get"]>;
export type QuerySandboxImagesResponse = JsonResponse<paths["/api/sandbox-images"]["get"]>;
export type QuerySandboxImagesData = NonNullable<QuerySandboxImagesResponse["data"]>;
export type SandboxImage = QuerySandboxImagesData["items"][number];
export type SandboxImageStatus = SandboxImage["status"];

export type CreateSandboxImageRequest = JsonRequestBody<paths["/api/sandbox-images"]["post"]>;
export type CreateSandboxImageResponse = JsonResponse<paths["/api/sandbox-images"]["post"]>;

export type SandboxImagePathParams = PathParameters<paths["/api/sandbox-images/{id}"]["delete"]>;
export type DeleteSandboxImageResponse = JsonResponse<paths["/api/sandbox-images/{id}"]["delete"]>;
export type CancelSandboxImagePathParams = PathParameters<paths["/api/sandbox-images/{id}/cancel"]["post"]>;
export type CancelSandboxImageResponse = JsonResponse<paths["/api/sandbox-images/{id}/cancel"]["post"]>;
export type RetrySandboxImagePathParams = PathParameters<paths["/api/sandbox-images/{id}/retry"]["post"]>;
export type RetrySandboxImageResponse = JsonResponse<paths["/api/sandbox-images/{id}/retry"]["post"]>;

export type QueryWorkProjectsParams = QueryParameters<paths["/api/work-projects"]["get"]>;
export type QueryWorkProjectsResponse = JsonResponse<paths["/api/work-projects"]["get"]>;
export type QueryWorkProjectsData = NonNullable<QueryWorkProjectsResponse["data"]>;
export type WorkProject = QueryWorkProjectsData["items"][number];
export type WorkProjectStatus = WorkProject["status"];
export type WorkProjectType = WorkProject["type"];

export type CreateWorkProjectRequest = JsonRequestBody<paths["/api/work-projects"]["post"]>;
export type CreateWorkProjectResponse = JsonResponse<paths["/api/work-projects"]["post"]>;

export type WorkProjectPathParams = PathParameters<paths["/api/work-projects/{id}"]["delete"]>;
export type DeleteWorkProjectResponse = JsonResponse<paths["/api/work-projects/{id}"]["delete"]>;
export type CancelWorkProjectPathParams = PathParameters<paths["/api/work-projects/{id}/cancel"]["post"]>;
export type CancelWorkProjectResponse = JsonResponse<paths["/api/work-projects/{id}/cancel"]["post"]>;
export type RetryWorkProjectPathParams = PathParameters<paths["/api/work-projects/{id}/retry"]["post"]>;
export type RetryWorkProjectResponse = JsonResponse<paths["/api/work-projects/{id}/retry"]["post"]>;

export type AgentSessionSummary = components["schemas"]["AgentSessionSummarySchema"];
export type SessionType = components["schemas"]["SessionTypeSchema"];

export type ListAgentSessionsResponse = JsonResponse<paths["/api/agent-sessions"]["get"]>;
export type ListAgentSessionsData = NonNullable<ListAgentSessionsResponse["data"]>;

export type CreateAgentSessionResponse = JsonResponse<paths["/api/agent-sessions"]["post"]>;
export type CreateAgentSessionData = NonNullable<CreateAgentSessionResponse["data"]>;

export type ListAgentEventsResponse = JsonResponse<paths["/api/agent-sessions/{session_id}/events"]["get"]>;
export type ListAgentEventsData = NonNullable<ListAgentEventsResponse["data"]>;
export type DeleteAgentSessionResponse = JsonResponse<paths["/api/agent-sessions/{session_id}"]["delete"]>;

export type UserMessageEvent = components["schemas"]["UserMessageEvent"];
export type TextDeltaEvent = components["schemas"]["TextDeltaEvent"];
export type TextCompleteEvent = components["schemas"]["TextCompleteEvent"];
export type ThinkingDeltaEvent = components["schemas"]["ThinkingDeltaEvent"];
export type ThinkingCompleteEvent = components["schemas"]["ThinkingCompleteEvent"];
export type ToolCallEvent = components["schemas"]["ToolCallEvent"];
export type ToolResultEvent = components["schemas"]["ToolResultEvent"];
export type HandoffEvent = components["schemas"]["HandoffEvent"];
export type ErrorEvent = components["schemas"]["ErrorEvent"];

export type AgentContentEvent = ListAgentEventsData["items"][number];
export type DoneEvent = { type: "done"; agent_name?: string };
export type AgentStreamEvent = AgentContentEvent | DoneEvent;
export type AgentEvent = AgentStreamEvent;
export type AgentEventType = AgentEvent["type"];

// websocket request payloads are out of OpenAPI scope, so this is the contract
export type AgentStreamCommand =
  | { action: "send"; text: string }
  | { action: "interrupt" };
