"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api, type ArticleDetail } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { CategoryBadge } from "@/components/category-badge";
import { SaveDialog } from "@/components/save-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { frDate } from "@/lib/utils";

export default function ArticlePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { user } = useSession();

  const [data, setData] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [isRead, setIsRead] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .article(id)
      .then((res) => {
        if (!alive) return;
        setData(res);
        setIsRead(res.is_read);
      })
      .catch(() => alive && setNotFound(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [id]);

  async function toggleRead() {
    const next = !isRead;
    setIsRead(next);
    try {
      await api.toggleRead(id, next);
    } catch {
      setIsRead(!next);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-3/4" />
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (notFound || !data) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card p-12 text-center text-muted-foreground">
        <p>Article introuvable.</p>
        <Link href="/" className="mt-3 inline-block">
          ← Retour aux articles
        </Link>
      </div>
    );
  }

  const a = data.article;
  const paragraphs = (a.summary || "").split("\n").filter((p) => p.trim());
  const loggedIn = data.logged_in && !!user;

  return (
    <article>
      <Link
        href="/"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-4 w-4" /> Articles
      </Link>

      <h2 className="mb-2 text-[22px] font-bold leading-tight tracking-tight text-foreground">
        {a.title}
      </h2>

      {a.title_original && a.title_original !== a.title && (
        <p className="mb-3 text-[13px] italic text-muted-foreground">
          Titre original : {a.title_original}
        </p>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-2 font-mono text-xs text-muted-foreground">
        <CategoryBadge category={a.category} slug={a.domain_slug} />
        <span>{a.source}</span>
        {a.published_at && <span>· {frDate(a.published_at)}</span>}
        {a.relevance ? (
          <Badge variant="relevance">pertinence {Math.round(a.relevance * 100)}%</Badge>
        ) : null}
        {data.crossed > 0 && <Badge>{data.crossed} sources croisées</Badge>}
      </div>

      {/* Actions (connecté) */}
      {loggedIn && (
        <div className="my-4 flex flex-wrap items-center gap-3 border-y border-border py-3">
          <SaveDialog
            articleId={a.id}
            folders={data.folders}
            initialSaved={!!data.saved}
            initialFolderId={data.saved?.folder_id ?? null}
            initialFolderName={data.saved_folder_name}
          />
          <Button variant="outline" size="sm" onClick={toggleRead}>
            {isRead ? "Marquer non lu" : "Marquer lu"}
          </Button>
        </div>
      )}

      {/* Résumé vulgarisé */}
      {paragraphs.length > 0 ? (
        <div className="space-y-3 text-[15.5px] leading-relaxed text-foreground">
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">Résumé en attente de traitement.</p>
      )}

      {/* Points à retenir */}
      {a.takeaways && a.takeaways.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 border-b border-border pb-1.5 text-[15px] font-semibold">
            À retenir
          </h3>
          <ul className="ml-5 list-disc space-y-1.5 text-[15px] text-foreground">
            {a.takeaways.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Lien officiel */}
      <div className="mt-7">
        <Button asChild>
          <a href={a.url} target="_blank" rel="noopener noreferrer" className="hover:no-underline">
            <ExternalLink /> Lire l&apos;article original
          </a>
        </Button>
      </div>

      {/* Sources croisées */}
      {data.duplicates.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-2 border-b border-border pb-1.5 text-[15px] font-semibold">
            Aussi couvert par
          </h3>
          <ul className="space-y-1.5 text-sm">
            {data.duplicates.map((d, i) => (
              <li key={i}>
                <a href={d.url} target="_blank" rel="noopener noreferrer">
                  {d.source}
                </a>
                <span className="text-muted-foreground"> — {d.title}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
