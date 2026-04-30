import { apiRequest } from "./client";
import { buildQuery } from "./query";
import { getStoredAccessToken } from "../auth/session";
import type {
  CreateSandboxContainerRequest,
  CreateSandboxContainerResponse,
  DeleteSandboxContainerResponse,
  QueryAvailableSandboxContainersParams,
  QueryAvailableSandboxContainersResponse,
  QuerySandboxContainersParams,
  QuerySandboxContainersResponse,
  SandboxContainerPathParams,
  StartSandboxContainerPathParams,
  StartSandboxContainerResponse,
  StopSandboxContainerPathParams,
  StopSandboxContainerResponse,
} from "./types";

const SANDBOX_CONTAINERS_PATH = "/api/sandbox-containers";

export function querySandboxContainers(params: QuerySandboxContainersParams) {
  return apiRequest<QuerySandboxContainersResponse>(`${SANDBOX_CONTAINERS_PATH}${buildQuery(params)}`);
}

export function queryAvailableSandboxContainers(params: QueryAvailableSandboxContainersParams) {
  return apiRequest<QueryAvailableSandboxContainersResponse>(`${SANDBOX_CONTAINERS_PATH}/available${buildQuery(params)}`);
}

export function createSandboxContainer(payload: CreateSandboxContainerRequest) {
  return apiRequest<CreateSandboxContainerResponse>(SANDBOX_CONTAINERS_PATH, {
    method: "POST",
    body: payload,
  });
}

export function startSandboxContainer(id: StartSandboxContainerPathParams["id"]) {
  return apiRequest<StartSandboxContainerResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/start`, {
    method: "POST",
  });
}

export function stopSandboxContainer(id: StopSandboxContainerPathParams["id"]) {
  return apiRequest<StopSandboxContainerResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/stop`, {
    method: "POST",
  });
}

export function deleteSandboxContainer(id: SandboxContainerPathParams["id"]) {
  return apiRequest<DeleteSandboxContainerResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}`, {
    method: "DELETE",
  });
}

export function buildContainerShellUrl(containerHash: string) {
  const token = getStoredAccessToken();
  if (!token) throw new Error("missing access token");
  const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${wsScheme}://${window.location.host}${SANDBOX_CONTAINERS_PATH}/${encodeURIComponent(containerHash)}/shell?token=${encodeURIComponent(token)}`;
}
