'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type ToastType = 'success' | 'error' | 'info';

export interface ToastData {
  type: ToastType;
  message: string;
}

/**
 * Tiny toast state hook: shows a message that auto-dismisses after a delay.
 * Returns the current toast (or null) together with show/dismiss helpers.
 */
export function useToast(autoDismissMs = 4500) {
  const [toast, setToast] = useState<ToastData | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback(
    (type: ToastType, message: string) => {
      setToast({ type, message });
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setToast(null), autoDismissMs);
    },
    [autoDismissMs],
  );

  const dismiss = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    setToast(null);
  }, []);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return { toast, showToast, dismiss };
}