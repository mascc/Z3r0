import { Button, Spin } from "@douyinfe/semi-ui";
import { ArrowDown } from "lucide-react";
import { ReactNode, RefObject, useRef } from "react";
import { useAutoFollowScroll } from "./useAutoFollowScroll";

type MessageScrollPanelProps = {
  ariaLabel: string;
  children: (tailRef: RefObject<HTMLDivElement | null>) => ReactNode;
  className?: string;
  contentClassName?: string;
  enabled?: boolean;
  loading?: boolean;
  resetKey?: string | number | null;
  scrollButtonClassName?: string;
  spinClassName?: string;
  watch?: readonly unknown[];
};

export function MessageScrollPanel({
  ariaLabel,
  children,
  className = "",
  contentClassName = "",
  enabled = true,
  loading = false,
  resetKey,
  scrollButtonClassName = "",
  spinClassName = "",
  watch = [],
}: MessageScrollPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const {
    following,
    tailRef,
    scrollHandlers,
    scrollToLatest,
  } = useAutoFollowScroll({
    enabled,
    containerRef,
    resetKey,
    watch,
  });

  return (
    <div className={`message-scroll-shell${className ? ` ${className}` : ""}`}>
      <div
        ref={containerRef}
        className={`message-scroll-viewport${contentClassName ? ` ${contentClassName}` : ""}`}
        aria-label={ariaLabel}
        {...scrollHandlers}
      >
        {loading ? (
          <Spin spinning wrapperClassName={`message-scroll-spin${spinClassName ? ` ${spinClassName}` : ""}`}>
            {children(tailRef)}
          </Spin>
        ) : (
          children(tailRef)
        )}
      </div>
      {enabled && !following ? (
        <Button
          className={`message-scroll-tail-floating${scrollButtonClassName ? ` ${scrollButtonClassName}` : ""}`}
          icon={<ArrowDown size={16} />}
          theme="solid"
          type="tertiary"
          onClick={scrollToLatest}
          aria-label="Scroll to latest message"
        />
      ) : null}
    </div>
  );
}
