import { cn, chipClass } from "@/lib/utils";

// Libellés courts pour les contextes contraints (tableau Sources).
const SHORT: Record<string, string> = {
  Tech: "Tech",
  "Business de la tech": "Business",
  "Data & IA": "Data & IA",
  "UX & solutions numériques": "UX",
};

export function CategoryBadge({
  category,
  slug,
  className,
  short = false,
}: {
  category: string | null;
  slug: string | null | undefined;
  className?: string;
  short?: boolean;
}) {
  const label = category
    ? short
      ? SHORT[category] ?? category
      : category
    : "Non classé";
  return (
    <span className={cn("chip-domain", chipClass(slug), className)} title={category ?? undefined}>
      {label}
    </span>
  );
}
