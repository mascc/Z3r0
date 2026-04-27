import { Button, Input, Modal, Select } from "@douyinfe/semi-ui";
import { KeyRound, Mail, Shield, User } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { getSystemUserRoles, isSystemUserRole } from "../../shared/api/contract";
import type { CreateSystemUserRequest, SystemUser, SystemUserRole, UpdateSystemUserRequest } from "../../shared/api/types";

type UserFormMode = "create" | "edit";

type UserFormValues = {
  username: string;
  email: string;
  password: string;
  role: SystemUserRole;
};

type UserFormModalProps =
  | {
      open: boolean;
      mode: "create";
      user: null;
      saving: boolean;
      onCancel: () => void;
      onSubmit: (payload: CreateSystemUserRequest) => Promise<void>;
    }
  | {
      open: boolean;
      mode: "edit";
      user: SystemUser;
      saving: boolean;
      onCancel: () => void;
      onSubmit: (payload: UpdateSystemUserRequest) => Promise<void>;
    };

const emptyValues: UserFormValues = {
  username: "",
  email: "",
  password: "",
  role: "user",
};

function buildInitialValues(user: SystemUser | null): UserFormValues {
  if (!user) {
    return emptyValues;
  }

  return {
    username: user.username,
    email: user.email,
    password: "",
    role: user.role,
  };
}

function buildCreatePayload(values: UserFormValues): CreateSystemUserRequest {
  return {
    username: values.username.trim(),
    email: values.email.trim(),
    role: values.role,
    password: values.password,
  };
}

function buildUpdatePayload(values: UserFormValues): UpdateSystemUserRequest {
  const basePayload = {
    username: values.username.trim(),
    email: values.email.trim(),
    role: values.role,
  };

  return values.password ? { ...basePayload, password: values.password } : basePayload;
}

export function UserFormModal({ open, mode, user, saving, onCancel, onSubmit }: UserFormModalProps) {
  const [values, setValues] = useState<UserFormValues>(() => buildInitialValues(user));
  const roles = useMemo(() => getSystemUserRoles(), []);

  useEffect(() => {
    if (open) {
      setValues(buildInitialValues(user));
    }
  }, [open, user]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "create") {
      await onSubmit(buildCreatePayload(values));
      return;
    }

    await onSubmit(buildUpdatePayload(values));
  };

  const handleRoleChange = (role: unknown) => {
    if (isSystemUserRole(role)) {
      setValues((current) => ({ ...current, role }));
    }
  };

  return (
    <Modal
      title={mode === "create" ? "Create User" : "Edit User"}
      visible={open}
      onCancel={onCancel}
      footer={null}
      width={520}
      maskClosable={!saving}
    >
      <form className="resource-form" onSubmit={handleSubmit}>
        <label>
          <span>Username</span>
          <Input
            type="text"
            prefix={<User size={16} />}
            value={values.username}
            onChange={(username) => setValues((current) => ({ ...current, username }))}
            maxLength={64}
            required
          />
        </label>
        <label>
          <span>Email</span>
          <Input
            type="email"
            prefix={<Mail size={16} />}
            value={values.email}
            onChange={(email) => setValues((current) => ({ ...current, email }))}
            maxLength={255}
          />
        </label>
        <label>
          <span>Role</span>
          <Select
            prefix={<Shield size={16} />}
            value={values.role}
            onChange={handleRoleChange}
            optionList={roles.map((role) => ({ label: role === "admin" ? "Admin" : "User", value: role }))}
          />
        </label>
        <label>
          <span>Password</span>
          <Input
            mode="password"
            prefix={<KeyRound size={16} />}
            value={values.password}
            onChange={(password) => setValues((current) => ({ ...current, password }))}
            maxLength={128}
            required={mode === "create"}
            placeholder={mode === "create" ? "Password" : "Leave blank to keep current password"}
          />
        </label>
        <div className="modal-actions">
          <Button onClick={onCancel} disabled={saving}>Cancel</Button>
          <Button htmlType="submit" theme="solid" type="danger" loading={saving}>
            {mode === "create" ? "Create" : "Save"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
