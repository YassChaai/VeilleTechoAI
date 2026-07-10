"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, type SourcesResponse } from "@/lib/api";
import { CategoryBadge } from "@/components/category-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useJob } from "@/lib/use-job";
import { frDate } from "@/lib/utils";

function pct(v: number | null) {
  return Math.round(Math.max(0, Math.min(1, v ?? 0)) * 100);
}

function Meter({ value }: { value: number | null }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-xs">
      <span className="h-1.5 w-14 overflow-hidden rounded-pill bg-secondary">
        <span className="block h-full rounded-pill bg-primary" style={{ width: `${pct(value)}%` }} />
      </span>
      {pct(value)}%
    </span>
  );
}

export default function SourcesPage() {
  const [data, setData] = useState<SourcesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const res = await api.sources();
    setData(res);
  }, []);

  useEffect(() => {
    load()
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [load]);

  const refresh = useJob({
    start: api.sourcesRefresh,
    poll: api.sourcesStatus,
    onDone: () => load(),
    initialRunning: !!data?.refresh_running,
  });

  const st = refresh.status;
  const discoveryOn = data?.discovery_enabled;

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[22px] font-bold tracking-tight">Sources</h2>
        <Button onClick={refresh.begin} disabled={refresh.running || !discoveryOn}>
          <RefreshCw className={refresh.running ? "animate-spin" : ""} /> Rafraîchir les sources
        </Button>
      </div>
      <p className="mb-5 text-[13px] text-muted-foreground">
        Socle imposé (5 sources justifiées) + découvertes autonomes (recherche web + LLM local),
        validées, notées et auto-élaguées.
        {!discoveryOn && " — Découverte désactivée (SOURCE_DISCOVERY=1 pour l'activer)."}
      </p>

      {(refresh.running || st) && (
        <div className="mb-6 rounded-lg border border-border bg-card p-4 shadow-card">
          <Progress value={st?.percent ?? 0} />
          <div className="mt-1.5 flex flex-wrap justify-between gap-3 font-mono text-xs text-muted-foreground">
            <span>{st?.phase || "En cours…"}</span>
            <span>
              {st?.found ?? 0} trouvées · {st?.validated ?? 0} validées · {st?.added ?? 0} ajoutées
              {st?.removed ? ` · ${st.removed} retirées` : ""}
            </span>
          </div>
        </div>
      )}

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="bg-secondary text-left font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2.5 font-semibold">Source</th>
                <th className="px-3 py-2.5 font-semibold">Domaine</th>
                <th className="px-3 py-2.5 font-semibold">Origine</th>
                <th className="px-3 py-2.5 font-semibold">Autorité</th>
                <th className="px-3 py-2.5 font-semibold">Qualité</th>
                <th className="px-3 py-2.5 font-semibold">État</th>
                <th className="px-3 py-2.5 text-right font-semibold">Vu le</th>
              </tr>
            </thead>
            <tbody>
              {(data?.sources ?? []).map((s) => (
                <tr
                  key={s.id}
                  className={`border-t border-border align-middle ${s.active ? "" : "opacity-55"}`}
                >
                  <td className="px-3 py-2.5">
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="font-medium">
                      {s.name}
                    </a>
                    <span className="ml-1.5 font-mono text-[11px] text-muted-foreground">
                      {s.type}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    {s.domain ? (
                      <CategoryBadge category={s.domain} slug={s.domain_slug} short />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <Badge variant={s.origin === "static" ? "primary" : "outline"}>
                      {s.origin === "static" ? "Socle" : "Découverte"}
                    </Badge>
                  </td>
                  <td className="px-3 py-2.5">
                    <Meter value={s.authority} />
                  </td>
                  <td className="px-3 py-2.5">
                    <Meter value={s.quality} />
                  </td>
                  <td className="px-3 py-2.5">
                    {s.active ? (
                      <span className="text-primary">actif</span>
                    ) : (
                      <span className="text-muted-foreground">élagué</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs text-muted-foreground">
                    {s.last_checked ? frDate(s.last_checked) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
