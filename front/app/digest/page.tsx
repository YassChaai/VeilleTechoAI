"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2, Sparkles } from "lucide-react";
import { api, type DigestResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useJob } from "@/lib/use-job";
import { cn, frDate } from "@/lib/utils";

export default function DigestPage() {
  const [data, setData] = useState<DigestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api.digest();
    setData(res);
    setSelected((prev) => prev ?? res.digests[0]?.week_start ?? null);
  }, []);

  useEffect(() => {
    load()
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [load]);

  const gen = useJob({
    start: () => api.generateDigest(),
    poll: api.digestStatus,
    onDone: () => {
      setSelected(null);
      load();
    },
    initialRunning: !!data?.generating,
  });

  const current = useMemo(
    () => data?.digests.find((d) => d.week_start === selected) ?? data?.digests[0] ?? null,
    [data, selected]
  );

  const hasCurrentWeek = data?.digests.some((d) => d.week_start === data.current_week);

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[22px] font-bold tracking-tight">Digest hebdomadaire</h2>
        <Button onClick={gen.begin} disabled={gen.running}>
          {gen.running ? (
            <>
              <Loader2 className="animate-spin" /> Rédaction…
            </>
          ) : (
            <>
              <Sparkles /> {hasCurrentWeek ? "Régénérer cette semaine" : "Générer cette semaine"}
            </>
          )}
        </Button>
      </div>
      <p className="mb-5 text-[13px] text-muted-foreground">
        Synthèse éditoriale rédigée par le modèle à partir des articles de la semaine, archivée
        chaque semaine (historique du dernier mois).
      </p>

      {gen.running && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground shadow-card">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          {gen.status?.phase || "Rédaction du digest en cours…"} (la rédaction peut prendre 1 à
          2 minutes)
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : data && data.digests.length > 0 ? (
        <>
          {/* Sélecteur de semaine (historique) */}
          <div className="mb-6 flex flex-wrap gap-2">
            {data.digests.map((d) => (
              <button
                key={d.week_start}
                onClick={() => setSelected(d.week_start)}
                className={cn(
                  "rounded-pill border px-3 py-1.5 text-[13px] font-medium transition-colors",
                  current?.week_start === d.week_start
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-muted-foreground hover:bg-secondary"
                )}
              >
                Semaine du {frDate(d.week_start)}
              </button>
            ))}
          </div>

          {current && (
            <article className="rounded-lg border border-border bg-card p-6 shadow-card sm:p-8">
              <div className="mb-5 flex flex-wrap items-center gap-2 border-b border-border pb-4 font-mono text-xs text-muted-foreground">
                <span>
                  {frDate(current.week_start)} → {frDate(current.week_end)}
                </span>
                <span>· {current.article_count} article(s)</span>
                {current.model && <Badge>{current.model}</Badge>}
                {current.generated_at && <span>· généré le {frDate(current.generated_at)}</span>}
              </div>
              <div className="markdown">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ node, href, children }) => {
                      const url = typeof href === "string" ? href : "";
                      return url.startsWith("/") ? (
                        <Link href={url}>{children}</Link>
                      ) : (
                        <a href={url} target="_blank" rel="noopener noreferrer">
                          {children}
                        </a>
                      );
                    },
                  }}
                >
                  {current.content}
                </ReactMarkdown>
              </div>
            </article>
          )}
        </>
      ) : (
        <div className="rounded-lg border border-dashed border-border bg-card p-12 text-center text-muted-foreground">
          <p>Aucun digest pour l&apos;instant.</p>
          <p className="mt-1 text-sm">
            Clique sur « Générer cette semaine » pour rédiger le premier, ou côté back :{" "}
            <code className="rounded bg-secondary px-1.5 py-0.5 font-mono">python main.py digest</code>
          </p>
        </div>
      )}
    </div>
  );
}
