import { Button, Popconfirm, Tag, Tooltip } from "@douyinfe/semi-ui";
import { Ban, Boxes, Fingerprint, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { cancelSandboxImage, createSandboxImage, deleteSandboxImage, querySandboxImages, retrySandboxImage } from "../../shared/api/sandboxImages";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CreateSandboxImageRequest, SandboxImage, SandboxImageStatus } from "../../shared/api/types";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { formatDateTime } from "../../shared/lib/date";
import { formatBytes } from "../../shared/lib/number";
import { SandboxImageFormModal } from "./SandboxImageFormModal";

const DEFAULT_PAGE_SIZE = 10;
const statusColorMap = { pulling: "amber", ready: "green", failed: "red", canceled: "grey" } satisfies Record<SandboxImageStatus, "amber" | "green" | "red" | "grey">;

type ModalState = { open: boolean };

function formatImageHash(imageHash: string) {
  return imageHash ? imageHash.slice(0, 12) : "Pending inspect";
}

function renderImageHash(imageHash: string) {
  const content = <>{formatImageHash(imageHash)}</>;
  return imageHash ? <Tooltip content={imageHash}>{content}</Tooltip> : content;
}

export function SandboxImagesPage() {
  const {
    items: images,
    page,
    keyword,
    loading,
    loadItems: loadImages,
    setKeyword,
    search,
    previous,
    next,
    canGoBack,
    canGoNext,
  } = usePagedResourceList<SandboxImage>({ pageSize: DEFAULT_PAGE_SIZE, query: querySandboxImages });
  const [saving, setSaving] = useState(false);
  const [cancelingImageId, setCancelingImageId] = useState<number | null>(null);
  const [deletingImageId, setDeletingImageId] = useState<number | null>(null);
  const [retryingImageId, setRetryingImageId] = useState<number | null>(null);
  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const setHeaderActions = useAdminHeaderActions();

  useEffect(() => {
    setHeaderActions(
      <>
        <Button icon={<RefreshCw size={16} />} onClick={() => void loadImages()} loading={loading} aria-label="Refresh sandbox images" />
        <Button icon={<Plus size={16} />} theme="solid" type="danger" onClick={() => setModalState({ open: true })}>
          Create Image
        </Button>
      </>,
    );
    return () => setHeaderActions(null);
  }, [loadImages, loading, setHeaderActions]);

  const imageSummary = useMemo(
    () => images.reduce(
      (summary, image) => ({
        ready: summary.ready + (image.status === "ready" ? 1 : 0),
        pulling: summary.pulling + (image.status === "pulling" ? 1 : 0),
        canceled: summary.canceled + (image.status === "canceled" ? 1 : 0),
      }),
      { ready: 0, pulling: 0, canceled: 0 },
    ),
    [images],
  );

  const handleCreate = async (payload: CreateSandboxImageRequest) => {
    setSaving(true);
    try {
      const response = await createSandboxImage(payload);
      showApiSuccess(response);
      setModalState({ open: false });
      await loadImages();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = async (image: SandboxImage) => {
    if (cancelingImageId !== null) {
      return;
    }

    setCancelingImageId(image.id);
    try {
      const response = await cancelSandboxImage(image.id);
      showApiSuccess(response);
      await loadImages();
    } catch (error) {
      showApiError(error);
    } finally {
      setCancelingImageId(null);
    }
  };

  const handleRetry = async (image: SandboxImage) => {
    if (retryingImageId !== null) {
      return;
    }

    setRetryingImageId(image.id);
    try {
      const response = await retrySandboxImage(image.id);
      showApiSuccess(response);
      await loadImages();
    } catch (error) {
      showApiError(error);
    } finally {
      setRetryingImageId(null);
    }
  };

  const handleDelete = async (image: SandboxImage) => {
    if (deletingImageId !== null) {
      return;
    }

    setDeletingImageId(image.id);
    try {
      const response = await deleteSandboxImage(image.id);
      showApiSuccess(response);
      await loadImages();
    } catch (error) {
      showApiError(error);
    } finally {
      setDeletingImageId(null);
    }
  };

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="Search image name, hash, or status"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total loaded", value: images.length },
          { label: "Ready", value: imageSummary.ready },
          { label: "Pulling", value: imageSummary.pulling },
          { label: "Canceled", value: imageSummary.canceled },
        ]}
        empty={images.length === 0}
        emptyIcon={<Boxes size={42} />}
        emptyTitle="No images found"
        page={page}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        onKeywordChange={setKeyword}
        onSearch={search}
        onPrevious={previous}
        onNext={next}
      >
        <div className="resource-table sandbox-images-table" role="table" aria-label="Sandbox images">
          <div className="resource-table-row resource-table-head" role="row">
            <div role="columnheader">Image</div>
            <div role="columnheader">Status</div>
            <div role="columnheader">Size</div>
            <div role="columnheader">Created</div>
            <div role="columnheader">Updated</div>
            <div role="columnheader">Actions</div>
          </div>
          {images.map((image) => (
            <div className="resource-table-row" role="row" key={image.id}>
              <div role="cell" className="image-identity">
                <div className="resource-avatar"><Boxes size={18} /></div>
                <div>
                  <strong>{image.image_name}</strong>
                  <span><Fingerprint size={13} />{renderImageHash(image.image_hash)}</span>
                </div>
              </div>
              <div role="cell"><Tag color={statusColorMap[image.status]}>{image.status}</Tag></div>
              <div role="cell">{formatBytes(image.image_size)}</div>
              <div role="cell">{formatDateTime(image.created_at)}</div>
              <div role="cell">{formatDateTime(image.updated_at)}</div>
              <div role="cell" className="row-actions">
                <Button
                  icon={<Ban size={15} />}
                  theme="borderless"
                  disabled={image.status !== "pulling"}
                  loading={cancelingImageId === image.id}
                  aria-label={`Cancel ${image.image_name}`}
                  onClick={() => void handleCancel(image)}
                />
                <Button
                  icon={<RotateCcw size={15} />}
                  theme="borderless"
                  disabled={image.status !== "failed" && image.status !== "canceled"}
                  loading={retryingImageId === image.id}
                  aria-label={`Retry ${image.image_name}`}
                  onClick={() => void handleRetry(image)}
                />
                <Popconfirm title="Delete image" content={`Delete ${image.image_name}?`} okType="danger" onConfirm={() => void handleDelete(image)}>
                  <Button
                    icon={<Trash2 size={15} />}
                    theme="borderless"
                    type="danger"
                    loading={deletingImageId === image.id}
                    aria-label={`Delete ${image.image_name}`}
                  />
                </Popconfirm>
              </div>
            </div>
          ))}
        </div>
      </ResourcePageShell>

      <SandboxImageFormModal
        open={modalState.open}
        saving={saving}
        onCancel={() => setModalState({ open: false })}
        onSubmit={handleCreate}
      />
    </>
  );
}
