"use client";

import Link from "next/link";
import { useState } from "react";
import { Bookmark, Star } from "lucide-react";
import { api, type Article } from "@/lib/api";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { CategoryBadge } from "./category-badge";
import { cn, frDate } from "@/lib/utils";

export function ArticleCard({
  article,
  loggedIn,
  crossed,
  onChanged,
}: {
  article: Article;
  loggedIn: boolean;
  crossed?: number;
  onChanged?: (saved: boolean) => void;
}) {
  const [saved, setSaved] = useState(!!article.saved);
  const [busy, setBusy] = useState(false);
  const isRead = loggedIn && !!article.read;

  async function toggleSave() {
    setBusy(true);
    try {
      if (saved) {
        await api.unsave(article.id);
        setSaved(false);
        onChanged?.(false);
      } else {
        await api.save(article.id, {});
        setSaved(true);
        onChanged?.(true);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      className={cn(
        "mb-3.5 p-4 transition-all hover:-translate-y-0.5 hover:shadow-hover",
        isRead && "opacity-60 hover:opacity-100"
      )}
    >
      <h3 className="mb-1.5 flex items-start gap-2 text-[16.5px] font-semibold leading-snug">
        {loggedIn && (
          <span
            className={cn(
              "mt-[7px] inline-block h-2 w-2 shrink-0 rounded-full border-[1.5px]",
              isRead ? "border-muted-foreground bg-muted-foreground" : "border-primary"
            )}
            title={isRead ? "Lu" : "Non lu"}
          />
        )}
        <Link
          href={`/article/${article.id}`}
          className="text-foreground hover:text-primary hover:no-underline"
        >
          {article.title}
        </Link>
      </h3>

      <div className="mb-2 flex flex-wrap items-center gap-2 font-mono text-xs text-muted-foreground">
        <CategoryBadge category={article.category} slug={article.domain_slug} />
        <span>{article.source}</span>
        {article.published_at && <span>· {frDate(article.published_at)}</span>}
        {crossed && crossed > 0 ? <Badge>{crossed} sources croisées</Badge> : null}
        {isRead && <Badge>lu</Badge>}
      </div>

      <p className="text-[15px] leading-relaxed text-foreground">{article.excerpt || "—"}</p>

      {loggedIn && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={toggleSave} disabled={busy}>
            {saved ? (
              <>
                <Star className="fill-current" /> Enregistré
              </>
            ) : (
              <>
                <Bookmark /> Lire plus tard
              </>
            )}
          </Button>
        </div>
      )}
    </Card>
  );
}
