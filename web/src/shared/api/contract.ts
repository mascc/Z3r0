import openApiSpec from "../../../openapi.json";
import type { SystemUserRole } from "./types";

const systemUserRoles = openApiSpec.components.schemas.SystemUserRoleSchema.enum;
const systemUserRoleValues = new Set<string>(systemUserRoles);

export function getSystemUserRoles(): SystemUserRole[] {
  return systemUserRoles.filter(isSystemUserRole);
}

export function isSystemUserRole(value: unknown): value is SystemUserRole {
  return typeof value === "string" && systemUserRoleValues.has(value);
}
