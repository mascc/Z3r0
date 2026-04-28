import { Button, Input, Modal, Select, TextArea } from "@douyinfe/semi-ui";
import { FolderKanban, ScanSearch } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { getWorkProjectTypes, isWorkProjectType } from "../../shared/api/contract";
import type { CreateWorkProjectRequest, WorkProjectType } from "../../shared/api/types";

type WorkProjectFormModalProps = {
  open: boolean;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (payload: CreateWorkProjectRequest) => Promise<void>;
};

const emptyValues: CreateWorkProjectRequest = {
  name: "",
  description: "",
  type: "penetration_test",
};

const workProjectTypeLabels = {
  penetration_test: "Penetration Test",
  source_code_audit: "Source Code Audit",
} satisfies Record<WorkProjectType, string>;

function buildPayload(values: CreateWorkProjectRequest): CreateWorkProjectRequest {
  return {
    name: values.name.trim(),
    description: values.description.trim(),
    type: values.type,
  };
}

export function WorkProjectFormModal({ open, saving, onCancel, onSubmit }: WorkProjectFormModalProps) {
  const [values, setValues] = useState<CreateWorkProjectRequest>(emptyValues);
  const projectTypes = useMemo(() => getWorkProjectTypes(), []);

  useEffect(() => {
    if (open) {
      setValues(emptyValues);
    }
  }, [open]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await onSubmit(buildPayload(values));
  };

  const handleTypeChange = (type: unknown) => {
    if (isWorkProjectType(type)) {
      setValues((current) => ({ ...current, type }));
    }
  };

  return (
    <Modal
      title="Create Work Project"
      visible={open}
      onCancel={onCancel}
      footer={null}
      width={560}
      maskClosable={!saving}
    >
      <form className="resource-form" onSubmit={handleSubmit}>
        <label>
          <span>Name</span>
          <Input
            type="text"
            prefix={<FolderKanban size={16} />}
            value={values.name}
            onChange={(name) => setValues((current) => ({ ...current, name }))}
            maxLength={255}
            required
          />
        </label>
        <label>
          <span>Type</span>
          <Select
            prefix={<ScanSearch size={16} />}
            value={values.type}
            onChange={handleTypeChange}
            optionList={projectTypes.map((type) => ({ label: workProjectTypeLabels[type], value: type }))}
          />
        </label>
        <label>
          <span>Description</span>
          <TextArea
            value={values.description}
            onChange={(description) => setValues((current) => ({ ...current, description }))}
            maxLength={2000}
            autosize={{ minRows: 3, maxRows: 6 }}
          />
        </label>
        <div className="modal-actions">
          <Button onClick={onCancel} disabled={saving}>Cancel</Button>
          <Button htmlType="submit" theme="solid" type="danger" loading={saving}>Create</Button>
        </div>
      </form>
    </Modal>
  );
}
