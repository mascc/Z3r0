import { RefObject, TouchEvent, WheelEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

type UseAutoFollowScrollOptions<T extends HTMLElement> = {
  enabled?: boolean;
  followLatest?: boolean;
  onFollowLatestChange?: (following: boolean) => void;
  onScrollToLatestReady?: (handler: (() => void) | null) => void;
  containerRef?: RefObject<T | null>;
  resetKey?: string | number | null;
  watch?: readonly unknown[];
};

export function useAutoFollowScroll<T extends HTMLElement = HTMLDivElement>({
  enabled = true,
  followLatest,
  onFollowLatestChange,
  onScrollToLatestReady,
  containerRef,
  resetKey,
  watch = [],
}: UseAutoFollowScrollOptions<T>) {
  const tailRef = useRef<HTMLDivElement | null>(null);
  const touchStartYRef = useRef<number | null>(null);
  const lastScrollTopRef = useRef(0);
  const [internalFollowLatest, setInternalFollowLatest] = useState(true);
  const following = followLatest ?? internalFollowLatest;

  const setFollowing = useCallback((next: boolean) => {
    if (followLatest === undefined) setInternalFollowLatest(next);
    onFollowLatestChange?.(next);
  }, [followLatest, onFollowLatestChange]);

  const getContainer = useCallback(() => {
    return containerRef?.current ?? findScrollContainer(tailRef.current);
  }, [containerRef]);

  const scrollTail = useCallback((behavior: ScrollBehavior) => {
    const container = getContainer();
    if (container) {
      container.scrollTo({ top: container.scrollHeight, behavior });
      if (behavior === "auto") lastScrollTopRef.current = container.scrollTop;
      return;
    }
    tailRef.current?.scrollIntoView({ behavior, block: "end" });
  }, [getContainer]);

  const scrollToLatest = useCallback(() => {
    setFollowing(true);
    scrollTail("smooth");
  }, [scrollTail, setFollowing]);

  useEffect(() => {
    if (resetKey == null) return;
    setFollowing(true);
    lastScrollTopRef.current = 0;
    touchStartYRef.current = null;
  }, [resetKey, setFollowing]);

  useEffect(() => {
    const container = enabled ? getContainer() : null;
    if (!container) {
      onScrollToLatestReady?.(null);
      return;
    }

    const syncFollowing = () => {
      const scrollingUp = container.scrollTop < lastScrollTopRef.current - 2;
      lastScrollTopRef.current = container.scrollTop;
      if (scrollingUp) {
        setFollowing(false);
        return;
      }
      if (isNearScrollTail(container)) setFollowing(true);
    };

    syncFollowing();
    onScrollToLatestReady?.(scrollToLatest);
    container.addEventListener("scroll", syncFollowing, { passive: true });
    return () => {
      container.removeEventListener("scroll", syncFollowing);
      onScrollToLatestReady?.(null);
    };
  }, [enabled, getContainer, onScrollToLatestReady, resetKey, scrollToLatest, setFollowing, ...watch]);

  useLayoutEffect(() => {
    if (!enabled || !following) return;
    scrollTail("auto");
    const frame = window.requestAnimationFrame(() => scrollTail("auto"));
    return () => window.cancelAnimationFrame(frame);
  }, [enabled, following, scrollTail, ...watch]);

  const pauseFollowing = useCallback(() => {
    if (following) setFollowing(false);
  }, [following, setFollowing]);

  const handleWheel = useCallback((event: WheelEvent<T>) => {
    if (event.deltaY < 0) pauseFollowing();
  }, [pauseFollowing]);

  const handleTouchStart = useCallback((event: TouchEvent<T>) => {
    touchStartYRef.current = event.touches[0]?.clientY ?? null;
  }, []);

  const handleTouchMove = useCallback((event: TouchEvent<T>) => {
    const startY = touchStartYRef.current;
    const currentY = event.touches[0]?.clientY;
    if (startY != null && currentY != null && currentY > startY) pauseFollowing();
  }, [pauseFollowing]);

  return {
    following,
    tailRef,
    scrollToLatest,
    scrollHandlers: {
      onWheel: handleWheel,
      onTouchStart: handleTouchStart,
      onTouchMove: handleTouchMove,
    },
  };
}

function isNearScrollTail(container: HTMLElement) {
  return container.scrollHeight - container.scrollTop - container.clientHeight < 72;
}

function findScrollContainer(element: HTMLElement | null) {
  let current = element?.parentElement ?? null;
  while (current) {
    const overflowY = window.getComputedStyle(current).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") return current;
    current = current.parentElement;
  }
  return null;
}
