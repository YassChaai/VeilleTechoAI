"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Download, Search } from "lucide-react";
import { api, type ArticlesResponse, type Meta } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { ArticleCard } from "@/components/article-card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useJob } from "@/lib/use-job";

const ALL = "__all__";

export default function ArticlesPage() {
  const { user } = useSession();
  const loggedIn = !!user;

  const [meta, setMeta] = useState<Meta | null>(null);
  const [q, setQ] = useState("");
  const [domain, setDomain] = useState(ALL);
  const [sort, setSort] = useState("date");
  const [read, setRead] = useState("");

  const [data, setData] = useState<ArticlesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.articles({
        q: q || undefined,
        domain: domain === ALL ? undefined : domain,
        sort,
        read: loggedIn && read ? read : undefined,
      });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, [q, domain, sort, read, loggedIn]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  // Adopte le filtre de lecture choisi par le serveur (préférence « masquer les lus »).
  useEffect(() => {
    if (loggedIn && read === "" && data?.read_filter) setRead(data.read_filter);
  }, [loggedIn, read, data]);

  const ingest = useJob({
    start: api.ingestRefresh,
    poll: api.ingestStatus,
    onDone: () => load(),
  });

  const st = ingest.status;

  return (
    <div>
      {/* Barre d'outils : recherche + filtres */}
      <div className="mb-5 flex flex-wrap gap-2.5">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            className="pl-9"
            placeholder="Rechercher (titre, résumé)…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        <Select value={domain} onValueChange={setDomain}>
          <SelectTrigger className="w-auto min-w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous les domaines</SelectItem>
            {(meta?.domains ?? []).map((d) => (
              <SelectItem key={d} value={d}>
                {d}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={sort} onValueChange={setSort}>
          <SelectTrigger className="w-auto min-w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="date">Trier : Date</SelectItem>
            <SelectItem value="relevance">Trier : Pertinence</SelectItem>
          </SelectContent>
        </Select>

        {loggedIn && (
          <Select value={read || "all"} onValueChange={setRead}>
            <SelectTrigger className="w-auto min-w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Lecture : Tous</SelectItem>
              <SelectItem value="unread">Lecture : Non lus</SelectItem>
              <SelectItem value="read">Lecture : Lus</SelectItem>
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Chercher de nouveaux articles (pipeline en arrière-plan) */}
      <div className="mb-6 rounded-lg border border-border bg-card p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={ingest.begin} disabled={ingest.running}>
            <Download /> Chercher de nouveaux articles
          </Button>
          <span className="text-[13px] text-muted-foreground">
            Récupère les derniers articles des sources actuelles (ingestion + résumé).
          </span>
        </div>
        {(ingest.running || st) && (
          <div className="mt-3">
            <Progress value={st?.percent ?? 0} />
            <div className="mt-1.5 flex justify-between gap-3 font-mono text-xs text-muted-foreground">
              <span>{st?.phase || "En cours…"}</span>
              <span>
                {st?.ingested ?? 0} nouveaux · {st?.summarized ?? 0} résumés
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Note / compteurs */}
      <div className="mb-4 text-[13px] text-muted-foreground">
        {data ? (
          <>
            {data.articles.length} article(s) affiché(s) · {data.total} en base
            {data.personalized && (
              <>
                {" · "}
                <Badge>réordonné par profil</Badge>
              </>
            )}
            {!loggedIn && (
              <>
                {" · "}
                <Link href="/login">connecte-toi</Link> pour suivre tes lectures et enregistrer des
                articles
              </>
            )}
          </>
        ) : (
          "Chargement…"
        )}
      </div>

      {/* Liste */}
      {error ? (
        <p className="rounded-lg border border-dashed border-border bg-card p-8 text-center text-muted-foreground">
          {error} — l&apos;API Flask est-elle lancée sur le port 5000 ?
        </p>
      ) : loading && !data ? (
        <div className="space-y-3.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : data && data.articles.length > 0 ? (
        data.articles.map((a) => <ArticleCard key={a.id} article={a} loggedIn={loggedIn} />)
      ) : (
        <p className="rounded-lg border border-dashed border-border bg-card p-12 text-center text-muted-foreground">
          Aucun article. Lance d&apos;abord le pipeline côté back :{" "}
          <code className="rounded bg-secondary px-1.5 py-0.5 font-mono">python main.py</code>
        </p>
      )}
    </div>
  );
}
