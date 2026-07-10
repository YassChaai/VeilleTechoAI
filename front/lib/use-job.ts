"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { JobStatus } from "@/lib/api";

interface Opts {
  start: () => Promise<unknown>;
  poll: () => Promise<JobStatus>;
  onDone?: (s: JobStatus) => void;
  initialRunning?: boolean;
}

/**
 * Suit une tâche de fond côté Flask (ingestion d'articles / découverte de
 * sources) : lance la tâche puis interroge son statut jusqu'à la fin.
 */
export function useJob({ start, poll, onDone, initialRunning }: Opts) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const cbs = useRef({ poll, onDone });
  cbs.current = { poll, onDone };
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loop = useCallback(async () => {
    try {
      const s = await cbs.current.poll();
      setStatus(s);
      if (s.done || (!s.running && (s.percent ?? 0) >= 100)) {
        setRunning(false);
        cbs.current.onDone?.(s);
        return;
      }
    } catch {
      /* on retente au prochain tick */
    }
    timer.current = setTimeout(loop, 900);
  }, []);

  const begin = useCallback(async () => {
    setRunning(true);
    setStatus({ running: true, done: false, percent: 4, phase: "Démarrage…" });
    try {
      await start();
    } catch {
      /* la boucle de statut remontera l'erreur éventuelle */
    }
    timer.current = setTimeout(loop, 700);
  }, [start, loop]);

  useEffect(() => {
    if (initialRunning) {
      setRunning(true);
      timer.current = setTimeout(loop, 300);
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [initialRunning, loop]);

  return { status, running, begin };
}
