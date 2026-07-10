import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-pill border px-2.5 py-0.5 text-[11px] font-semibold font-mono tracking-wide whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-border bg-secondary text-muted-foreground",
        primary: "border-primary bg-primary text-primary-foreground",
        outline: "border-border text-muted-foreground",
        relevance: "chip-relevance",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
