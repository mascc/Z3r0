import { Button, Input, Modal } from "@douyinfe/semi-ui";
import { Package } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import type { CreateSandboxImageRequest } from "../../shared/api/types";

type SandboxImageFormModalProps = {
  open: boolean;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (payload: CreateSandboxImageRequest) => Promise<void>;
};

const emptyValues: CreateSandboxImageRequest = {
  image_name: "",
};

function buildPayload(values: CreateSandboxImageRequest): CreateSandboxImageRequest {
  return {
    image_name: values.image_name.trim(),
  };
}

export function SandboxImageFormModal({ open, saving, onCancel, onSubmit }: SandboxImageFormModalProps) {
  const [values, setValues] = useState<CreateSandboxImageRequest>(emptyValues);

  useEffect(() => {
    if (open) {
      setValues(emptyValues);
    }
  }, [open]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await onSubmit(buildPayload(values));
  };

  return (
    <Modal
      title="Create Sandbox Image"
      visible={open}
      onCancel={onCancel}
      footer={null}
      width={520}
      maskClosable={!saving}
    >
      <form className="resource-form" onSubmit={handleSubmit}>
        <label>
          <span>Image Name</span>
          <Input
            type="text"
            prefix={<Package size={16} />}
            value={values.image_name}
            onChange={(image_name) => setValues({ image_name })}
            placeholder="ghcr.io/org/image:latest"
            maxLength={255}
            required
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
