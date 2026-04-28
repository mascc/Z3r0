import { apiRequest } from "./client";
import { buildQuery } from "./query";
import type {
  CancelWorkProjectPathParams,
  CancelWorkProjectResponse,
  CreateWorkProjectRequest,
  CreateWorkProjectResponse,
  DeleteWorkProjectResponse,
  QueryWorkProjectsParams,
  QueryWorkProjectsResponse,
  RetryWorkProjectPathParams,
  RetryWorkProjectResponse,
  WorkProjectPathParams,
} from "./types";

const WORK_PROJECTS_PATH = "/api/work-projects";

export function queryWorkProjects(params: QueryWorkProjectsParams) {
  return apiRequest<QueryWorkProjectsResponse>(`${WORK_PROJECTS_PATH}${buildQuery(params)}`);
}

export function createWorkProject(payload: CreateWorkProjectRequest) {
  return apiRequest<CreateWorkProjectResponse>(WORK_PROJECTS_PATH, {
    method: "POST",
    body: payload,
  });
}

export function cancelWorkProject(id: CancelWorkProjectPathParams["id"]) {
  return apiRequest<CancelWorkProjectResponse>(`${WORK_PROJECTS_PATH}/${id}/cancel`, {
    method: "POST",
  });
}

export function retryWorkProject(id: RetryWorkProjectPathParams["id"]) {
  return apiRequest<RetryWorkProjectResponse>(`${WORK_PROJECTS_PATH}/${id}/retry`, {
    method: "POST",
  });
}

export function deleteWorkProject(id: WorkProjectPathParams["id"]) {
  return apiRequest<DeleteWorkProjectResponse>(`${WORK_PROJECTS_PATH}/${id}`, {
    method: "DELETE",
  });
}
