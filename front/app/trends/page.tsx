"use client";

import { useEffect, useState } from "react";
import { Sparkles, TrendingUp } from "lucide-react";
import { api, type TrendItem, type TrendsResponse } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { ArticleCard } from "@/components/article-card";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

function TrendCard({ t, onOpen }: { t: TrendItem; onOpen: (t: TrendItem) => void }) {
  const count = t.articles?.length ?? 0;
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onOpen(t)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen(t)}
      className="group cursor-pointer p-4 transition-all hover:-translate-y-0.5 hover:shadow-hover"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-mono text-[15px] font-semibold text-primary underline-offset-2 group-hover:underline">
          {t.term}
        </h3>
        <span className="font-mono text-xs text-muted-foreground">×{t.lift}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-2">
        <Badge>{t.recent} récentes</Badge>
        <Badge>
          {t.sources} source{t.sources > 1 ? "s" : ""}
        </Badge>
        {t.baseline > 0 && <Badge variant="outline">{t.baseline} avant</Badge>}
        {count > 0 && (
          <Badge variant="outline">
            {count} article{count > 1 ? "s" : ""} →
          </Badge>
        )}
      </div>
    </Card>
  );
}

export default function TrendsPage() {
  const { user } = useSession();
  const [data, setData] = useState<TrendsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [openTerm, setOpenTerm] = useState<TrendItem | null>(null);

  useEffect(() => {
    api
      .trends()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  const grid = (items: TrendItem[]) => (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map((t) => (
        <TrendCard key={t.term} t={t} onOpen={setOpenTerm} />
      ))}
    </div>
  );

  return (
    <div>
      <h2 className="mb-1 text-[22px] font-bold tracking-tight">Tendances &amp; signaux faibles</h2>
      <p className="mb-6 text-[13px] text-muted-foreground">
        Termes qui montent sur {data?.recent_days ?? 7} jours vs une base de 30 jours.{" "}
        <span className="text-foreground">Clique un terme</span> pour voir les articles liés.
      </p>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <>
          <section className="mb-8">
            <h3 className="mb-3 flex items-center gap-2 border-b border-border pb-2 text-[15px] font-semibold">
              <TrendingUp className="h-4 w-4 text-primary" /> Tendances (≥ 2 sources)
            </h3>
            {data && data.trends.length > 0 ? (
              grid(data.trends)
            ) : (
              <p className="text-sm text-muted-foreground">
                Pas encore assez de données. Lance quelques ingestions.
              </p>
            )}
          </section>

          <section>
            <h3 className="mb-3 flex items-center gap-2 border-b border-border pb-2 text-[15px] font-semibold">
              <Sparkles className="h-4 w-4 text-primary" /> Signaux faibles (émergents)
            </h3>
            {data && data.weak.length > 0 ? (
              grid(data.weak)
            ) : (
              <p className="text-sm text-muted-foreground">
                Aucun signal faible détecté pour l&apos;instant.
              </p>
            )}
          </section>
        </>
      )}

      {/* Pop-up : articles liés au terme */}
      <Dialog open={!!openTerm} onOpenChange={(o) => !o && setOpenTerm(null)}>
        <DialogContent className="max-h-[82vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-mono text-primary">{openTerm?.term}</DialogTitle>
            <DialogDescription>
              {openTerm?.recent} mention(s) récente(s) · {openTerm?.sources} source(s) ·{" "}
              {openTerm?.articles?.length ?? 0} article(s) lié(s)
            </DialogDescription>
          </DialogHeader>
          <div className="mt-1">
            {openTerm?.articles && openTerm.articles.length > 0 ? (
              openTerm.articles.map((a) => (
                <ArticleCard key={a.id} article={a} loggedIn={!!user} />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Aucun article lié.</p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
