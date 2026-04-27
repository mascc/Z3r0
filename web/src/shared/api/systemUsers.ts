import { apiRequest } from "./client";
import type {
  CreateSystemUserRequest,
  CreateSystemUserResponse,
  DeleteSystemUserResponse,
  LoginRequest,
  LoginResponse,
  QuerySystemUsersParams,
  QuerySystemUsersResponse,
  SystemUserPathParams,
  UpdateSystemUserRequest,
  UpdateSystemUserResponse,
} from "./types";

const SYSTEM_USERS_PATH = "/api/system-users";

function buildQuery(params: QuerySystemUsersParams) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  });
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export function login(payload: LoginRequest) {
  return apiRequest<LoginResponse>(`${SYSTEM_USERS_PATH}/login`, {
    method: "POST",
    body: payload,
    auth: false,
  });
}

export function querySystemUsers(params: QuerySystemUsersParams) {
  return apiRequest<QuerySystemUsersResponse>(`${SYSTEM_USERS_PATH}${buildQuery(params)}`);
}

export function createSystemUser(payload: CreateSystemUserRequest) {
  return apiRequest<CreateSystemUserResponse>(SYSTEM_USERS_PATH, {
    method: "POST",
    body: payload,
  });
}

export function updateSystemUser(id: SystemUserPathParams["id"], payload: UpdateSystemUserRequest) {
  return apiRequest<UpdateSystemUserResponse>(`${SYSTEM_USERS_PATH}/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteSystemUser(id: SystemUserPathParams["id"]) {
  return apiRequest<DeleteSystemUserResponse>(`${SYSTEM_USERS_PATH}/${id}`, {
    method: "DELETE",
  });
}
