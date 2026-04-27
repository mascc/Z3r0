import type { paths } from "./generated/schema";

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

export type CommonResponsePayload = {
  code?: number;
  message?: string;
  data?: unknown;
};

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
