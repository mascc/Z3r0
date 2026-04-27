import { apiRequest } from "./client";
import { buildQuery } from "./query";
import type {
  CancelSandboxImagePathParams,
  CancelSandboxImageResponse,
  CreateSandboxImageRequest,
  CreateSandboxImageResponse,
  DeleteSandboxImageResponse,
  QuerySandboxImagesParams,
  QuerySandboxImagesResponse,
  RetrySandboxImagePathParams,
  RetrySandboxImageResponse,
  SandboxImagePathParams,
} from "./types";

const SANDBOX_IMAGES_PATH = "/api/sandbox-images";

export function querySandboxImages(params: QuerySandboxImagesParams) {
  return apiRequest<QuerySandboxImagesResponse>(`${SANDBOX_IMAGES_PATH}${buildQuery(params)}`);
}

export function createSandboxImage(payload: CreateSandboxImageRequest) {
  return apiRequest<CreateSandboxImageResponse>(SANDBOX_IMAGES_PATH, {
    method: "POST",
    body: payload,
  });
}

export function cancelSandboxImage(id: CancelSandboxImagePathParams["id"]) {
  return apiRequest<CancelSandboxImageResponse>(`${SANDBOX_IMAGES_PATH}/${id}/cancel`, {
    method: "POST",
  });
}

export function retrySandboxImage(id: RetrySandboxImagePathParams["id"]) {
  return apiRequest<RetrySandboxImageResponse>(`${SANDBOX_IMAGES_PATH}/${id}/retry`, {
    method: "POST",
  });
}

export function deleteSandboxImage(id: SandboxImagePathParams["id"]) {
  return apiRequest<DeleteSandboxImageResponse>(`${SANDBOX_IMAGES_PATH}/${id}`, {
    method: "DELETE",
  });
}
