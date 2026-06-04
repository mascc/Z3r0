import { Select, Switch, TextArea } from "@douyinfe/semi-ui";
import { Boxes } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { generateDefaultSandboxContainerPortMappings } from "../../shared/api/sandboxContainers";
import { showApiError } from "../../shared/api/feedback";
import type { CreateSandboxContainerRequest, SandboxImage } from "../../shared/api/types";
import { SANDBOX_CONTAINER_DEFAULT_COMMAND } from "../../shared/api/generated/constants";
import { ResourceModal } from "../../shared/components/ResourceModal";
import { createClientId } from "../../shared/lib/id";
import {
  createEmptyPortMapping,
  PortMappingEditor,
  type PortMappingFormValue,
} from "./PortMappingEditor";

type SandboxContainerFormModalProps = {
  open: boolean;
  saving: boolean;
  images: SandboxImage[];
  imagesLoading: boolean;
  onCancel: () => void;
  onSubmit: (payload: CreateSandboxContainerRequest) => Promise<void>;
};

const DEFAULT_NOVNC_PORT = 8000;

export function SandboxContainerFormModal({
  open,
  saving,
  images,
  imagesLoading,
  onCancel,
  onSubmit,
}: SandboxContainerFormModalProps) {
  const readyImages = useMemo(() => images.filter((image) => image.status === "ready"), [images]);
  const [imageId, setImageId] = useState<number | undefined>();
  const [containerCommand, setContainerCommand] = useState(SANDBOX_CONTAINER_DEFAULT_COMMAND);
  const [portMappings, setPortMappings] = useState<PortMappingFormValue[]>([]);
  const [portMappingsLoading, setPortMappingsLoading] = useState(false);
  const [novncSupport, setNoVNCSupport] = useState(false);
  const [novncPort, setNoVNCPort] = useState<number | undefined>();
  const portMappingRequestId = useRef(0);

  useEffect(() => {
    if (!open) return;
    setImageId(readyImages[0]?.id);
    setContainerCommand(SANDBOX_CONTAINER_DEFAULT_COMMAND);
    setPortMappings([]);
    setPortMappingsLoading(false);
    setNoVNCSupport(false);
    setNoVNCPort(undefined);
  }, [open, readyImages]);

  const loadDefaultPortMappings = useCallback(async (nextImageId: number) => {
    const requestId = portMappingRequestId.current + 1;
    portMappingRequestId.current = requestId;
    setPortMappingsLoading(true);
    setPortMappings([]);
    try {
      const response = await generateDefaultSandboxContainerPortMappings({ image_id: nextImageId });
      if (portMappingRequestId.current !== requestId) return;
      setPortMappings((response.data?.port_mappings ?? []).map((mapping) => ({
        id: createClientId("port-mapping"),
        ...mapping,
      })));
    } catch (error) {
      if (portMappingRequestId.current !== requestId) return;
      setPortMappings([]);
      showApiError(error);
    } finally {
      if (portMappingRequestId.current === requestId) setPortMappingsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || imageId === undefined) return;
    void loadDefaultPortMappings(imageId);
  }, [imageId, loadDefaultPortMappings, open]);

  const tcpContainerPorts = useMemo(() => {
    const ports = new Set<number>();
    portMappings.forEach((mapping) => {
      if (mapping.protocol === "tcp" && mapping.container_port >= 1 && mapping.container_port <= 65535) {
        ports.add(mapping.container_port);
      }
    });
    return [...ports].sort((left, right) => left - right);
  }, [portMappings]);

  const preferredNoVNCPort = useMemo(() => (
    tcpContainerPorts.includes(DEFAULT_NOVNC_PORT) ? DEFAULT_NOVNC_PORT : tcpContainerPorts[0]
  ), [tcpContainerPorts]);

  const noVNCPortOptions = useMemo(() => tcpContainerPorts.map((port) => ({
    label: `${port}/tcp`,
    value: port,
  })), [tcpContainerPorts]);

  useEffect(() => {
    if (!open) return;
    if (!novncSupport) {
      setNoVNCPort(undefined);
      return;
    }
    setNoVNCPort((current) => (
      current !== undefined && tcpContainerPorts.includes(current) ? current : preferredNoVNCPort
    ));
  }, [novncSupport, open, preferredNoVNCPort, tcpContainerPorts]);

  const novncPortValid = !novncSupport || (
    novncPort !== undefined && tcpContainerPorts.includes(novncPort)
  );

  const submit = () => onSubmit({
    image_id: imageId || 0,
    container_command: containerCommand.trim(),
    novnc_support: novncSupport,
    novnc_port: novncSupport ? (novncPort ?? 0) : 0,
    port_mappings: portMappings.map(({ container_port, host_port, protocol }) => ({
      container_port,
      host_port,
      protocol,
    })),
  });

  const updateMapping = (id: string, patch: Partial<PortMappingFormValue>) => {
    setPortMappings((current) => current.map((mapping) => (
      mapping.id === id ? { ...mapping, ...patch } : mapping
    )));
  };

  const removeMapping = (id: string) => {
    setPortMappings((current) => current.filter((item) => item.id !== id));
  };

  const addMapping = () => {
    setPortMappings((current) => [...current, createEmptyPortMapping()]);
  };

  const selectImage = (value: unknown) => {
    if (typeof value === "number") setImageId(value);
  };

  const selectNoVNCPort = (value: unknown) => {
    if (typeof value === "number") setNoVNCPort(value);
  };

  const toggleNoVNCSupport = (checked: boolean) => {
    setNoVNCSupport(checked);
    setNoVNCPort((current) => (
      checked && current !== undefined && tcpContainerPorts.includes(current) ? current : preferredNoVNCPort
    ));
  };

  const submitDisabled = !imageId || portMappingsLoading || !novncPortValid;

  return (
    <ResourceModal
      open={open}
      title="Create Sandbox Container"
      saving={saving}
      submitLabel="Create"
      submitDisabled={submitDisabled}
      width={640}
      onCancel={onCancel}
      onSubmit={submit}
    >
      <label>
        <span>Image</span>
        <Select
          prefix={<Boxes size={16} />}
          value={imageId}
          loading={imagesLoading}
          disabled={readyImages.length === 0}
          placeholder="Select a ready sandbox image"
          onChange={selectImage}
          optionList={readyImages.map((image) => ({ label: image.image_name, value: image.id }))}
        />
      </label>

      <label>
        <span>Command</span>
        <TextArea
          value={containerCommand}
          maxLength={2000}
          autosize={{ minRows: 3, maxRows: 6 }}
          onChange={setContainerCommand}
        />
      </label>

      <div className="novnc-toggle-row">
        <span>noVNC</span>
        <div className="novnc-controls">
          <Switch checked={novncSupport} onChange={toggleNoVNCSupport} aria-label="Enable noVNC" />
          {novncSupport ? (
            <label className="novnc-port-field">
              <span>noVNC Port</span>
              <Select
                value={novncPort}
                disabled={portMappingsLoading || noVNCPortOptions.length === 0}
                placeholder={noVNCPortOptions.length === 0 ? "No TCP ports mapped" : "Select mapped TCP port"}
                optionList={noVNCPortOptions}
                onChange={selectNoVNCPort}
              />
            </label>
          ) : null}
        </div>
      </div>

      <PortMappingEditor
        mappings={portMappings}
        loading={portMappingsLoading}
        canLoadDefaults={imageId !== undefined}
        onAdd={addMapping}
        onLoadDefaults={() => imageId !== undefined && void loadDefaultPortMappings(imageId)}
        onRemove={removeMapping}
        onChange={updateMapping}
      />
    </ResourceModal>
  );
}
