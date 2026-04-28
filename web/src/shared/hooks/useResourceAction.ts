import { useCallback, useState } from "react";
import { showApiError, showApiSuccess } from "../api/feedback";
import type { CommonResponsePayload } from "../api/types";

export function useResourceAction<Item extends { id: number }>(
  action: (item: Item) => Promise<CommonResponsePayload>,
  onAfter?: () => void | Promise<void>,
) {
  const [busyId, setBusyId] = useState<number | null>(null);

  const run = useCallback(
    async (item: Item) => {
      if (busyId !== null) return;
      setBusyId(item.id);
      try {
        const response = await action(item);
        showApiSuccess(response);
        await onAfter?.();
      } catch (error) {
        showApiError(error);
      } finally {
        setBusyId(null);
      }
    },
    [action, busyId, onAfter],
  );

  return { run, busyId };
}
