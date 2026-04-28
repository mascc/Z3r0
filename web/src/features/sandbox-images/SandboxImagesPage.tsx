import { Button, Popconfirm, Tag, Tooltip } from "@douyinfe/semi-ui";
import type { TagColor } from "@douyinfe/semi-ui/lib/es/tag";
import { Ban, Boxes, Fingerprint, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { cancelSandboxImage, createSandboxImage, deleteSandboxImage, querySandboxImages, retrySandboxImage } from "../../shared/api/sandboxImages";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { CreateSandboxImageRequest, SandboxImage, SandboxImageStatus } from "../../shared/api/types";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceAction } from "../../shared/hooks/useResourceAction";
import { formatDateTime } from "../../shared/lib/date";
import { formatBytes } from "../../shared/lib/number";
import { SandboxImageFormModal } from "./SandboxImageFormModal";

const DEFAULT_PAGE_SIZE = 10;
const statusColorMap: Record<SandboxImageStatus, TagColor> = { pulling: "amber", ready: "green", failed: "red", canceled: "grey" };

function renderImageHash(imageHash: string) {
  if (!imageHash) return <>Pending inspect</>;
  return <Tooltip content={imageHash}>{imageHash.slice(0, 12)}</Tooltip>;
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
  const [modalOpen, setModalOpen] = useState(false);
  const setHeaderActions = useAdminHeaderActions();

  const { run: cancelImage, busyId: cancelingId } = useResourceAction<SandboxImage>(
    (image) => cancelSandboxImage(image.id),
    loadImages,
  );
  const { run: retryImage, busyId: retryingId } = useResourceAction<SandboxImage>(
    (image) => retrySandboxImage(image.id),
    loadImages,
  );
  const { run: deleteImage, busyId: deletingId } = useResourceAction<SandboxImage>(
    (image) => deleteSandboxImage(image.id),
    loadImages,
  );

  useEffect(() => {
    setHeaderActions(
      <>
        <Button icon={<RefreshCw size={16} />} onClick={() => void loadImages()} loading={loading} aria-label="Refresh sandbox images" />
        <Button icon={<Plus size={16} />} theme="solid" type="danger" onClick={() => setModalOpen(true)}>
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
      setModalOpen(false);
      await loadImages();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
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
                  loading={cancelingId === image.id}
                  aria-label={`Cancel ${image.image_name}`}
                  onClick={() => void cancelImage(image)}
                />
                <Button
                  icon={<RotateCcw size={15} />}
                  theme="borderless"
                  disabled={image.status !== "failed" && image.status !== "canceled"}
                  loading={retryingId === image.id}
                  aria-label={`Retry ${image.image_name}`}
                  onClick={() => void retryImage(image)}
                />
                <Popconfirm title="Delete image" content={`Delete ${image.image_name}?`} okType="danger" onConfirm={() => void deleteImage(image)}>
                  <Button
                    icon={<Trash2 size={15} />}
                    theme="borderless"
                    type="danger"
                    loading={deletingId === image.id}
                    aria-label={`Delete ${image.image_name}`}
                  />
                </Popconfirm>
              </div>
            </div>
          ))}
        </div>
      </ResourcePageShell>

      <SandboxImageFormModal
        open={modalOpen}
        saving={saving}
        onCancel={() => setModalOpen(false)}
        onSubmit={handleCreate}
      />
    </>
  );
}
