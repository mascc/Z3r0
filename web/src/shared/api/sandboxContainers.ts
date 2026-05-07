import { apiRequest } from "./client";
import { buildQuery } from "./query";
import { getStoredAccessToken } from "../auth/session";
import type {
  CreateSandboxContainerRequest,
  CreateSandboxContainerResponse,
  DeleteSandboxContainerResponse,
  GenerateDefaultSandboxContainerPortMappingsParams,
  GenerateDefaultSandboxContainerPortMappingsResponse,
  QueryAvailableSandboxContainersParams,
  QueryAvailableSandboxContainersResponse,
  QuerySandboxContainersParams,
  QuerySandboxContainersResponse,
  SandboxContainer,
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

export function generateDefaultSandboxContainerPortMappings(params: GenerateDefaultSandboxContainerPortMappingsParams) {
  return apiRequest<GenerateDefaultSandboxContainerPortMappingsResponse>(`${SANDBOX_CONTAINERS_PATH}/default-port-mappings${buildQuery(params)}`);
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

export function getContainerNoVNCPortMapping(container: SandboxContainer) {
  if (!container.novnc_support || !container.novnc_port) return undefined;
  return container.port_mappings.find((item) => (
    item.protocol === "tcp" && item.container_port === container.novnc_port
  ));
}

export function canOpenContainerNoVNC(container: SandboxContainer) {
  return Boolean(getContainerNoVNCPortMapping(container));
}

export function buildContainerNoVNCUrl(container: SandboxContainer) {
  const mapping = getContainerNoVNCPortMapping(container);
  if (!mapping) {
    throw new Error("missing noVNC port mapping");
  }

  const url = new URL(window.location.href);
  url.port = String(mapping.host_port);
  url.pathname = "/novnc/vnc.html";
  url.search = "";
  url.hash = "";
  url.searchParams.set("autoconnect", "true");
  url.searchParams.set("resize", "remote");
  url.searchParams.set("path", "websockify");
  return url.toString();
}
