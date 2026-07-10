import * as React from "react";
import { cn } from "@/lib/utils";

/** Barre de progression simple (rafraîchissement sources / ingestion). */
export function Progress({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value || 0));
  return (
    <div
      className={cn(
        "h-2.5 w-full overflow-hidden rounded-pill border border-border bg-secondary",
        className
      )}
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-pill bg-primary transition-all duration-300 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
