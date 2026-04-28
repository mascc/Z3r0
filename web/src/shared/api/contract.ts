import openApiSpec from "../../../openapi.json";
import type { SystemUserRole, WorkProjectType } from "./types";

const systemUserRoles = openApiSpec.components.schemas.SystemUserRoleSchema.enum;
const systemUserRoleValues = new Set<string>(systemUserRoles);
const workProjectTypes = openApiSpec.components.schemas.WorkProjectTypeSchema.enum;
const workProjectTypeValues = new Set<string>(workProjectTypes);

export function getSystemUserRoles(): SystemUserRole[] {
  return systemUserRoles.filter(isSystemUserRole);
}

export function isSystemUserRole(value: unknown): value is SystemUserRole {
  return typeof value === "string" && systemUserRoleValues.has(value);
}

export function getWorkProjectTypes(): WorkProjectType[] {
  return workProjectTypes.filter(isWorkProjectType);
}

export function isWorkProjectType(value: unknown): value is WorkProjectType {
  return typeof value === "string" && workProjectTypeValues.has(value);
}
