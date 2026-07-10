"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FolderPlus, Trash2 } from "lucide-react";
import { api, type LibraryResponse } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { ArticleCard } from "@/components/article-card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export default function LibraryPage() {
  const { user, loading: sessionLoading } = useSession();
  const [data, setData] = useState<LibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [newFolder, setNewFolder] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.library());
    } catch {
      /* non connecté : géré par le garde ci-dessous */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!sessionLoading && user) load();
    else if (!sessionLoading) setLoading(false);
  }, [sessionLoading, user, load]);

  async function createFolder(e: React.FormEvent) {
    e.preventDefault();
    if (!newFolder.trim()) return;
    setBusy(true);
    try {
      await api.createFolder(newFolder.trim());
      setNewFolder("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function deleteFolder(id: number) {
    await api.deleteFolder(id);
    await load();
  }

  if (!sessionLoading && !user) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card p-12 text-center text-muted-foreground">
        <p>La bibliothèque est réservée aux comptes.</p>
        <Link href="/login" className="mt-3 inline-block">
          Se connecter
        </Link>{" "}
        ou{" "}
        <Link href="/register" className="inline-block">
          créer un compte
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[22px] font-bold tracking-tight">Bibliothèque</h2>
        {data && <span className="text-sm text-muted-foreground">{data.total} enregistré(s)</span>}
      </div>

      <form onSubmit={createFolder} className="mb-7 mt-3 flex max-w-md gap-2">
        <Input
          placeholder="Nouveau dossier thématique…"
          value={newFolder}
          onChange={(e) => setNewFolder(e.target.value)}
        />
        <Button type="submit" variant="secondary" disabled={busy}>
          <FolderPlus /> Créer
        </Button>
      </form>

      {loading ? (
        <div className="space-y-3.5">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : data ? (
        <>
          <section className="mb-8">
            <h3 className="mb-3 border-b border-border pb-2 text-[15px] font-semibold">
              À lire{" "}
              <span className="font-normal text-muted-foreground">({data.unfiled.length})</span>
            </h3>
            {data.unfiled.length > 0 ? (
              data.unfiled.map((a) => (
                <ArticleCard key={a.id} article={{ ...a, saved: true }} loggedIn onChanged={load} />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Aucun article non classé.</p>
            )}
          </section>

          {data.folders.map((f) => (
            <section key={f.id} className="mb-8">
              <div className="mb-3 flex items-center justify-between gap-3 border-b border-border pb-2">
                <h3 className="text-[15px] font-semibold">
                  {f.name} <span className="font-normal text-muted-foreground">({f.count})</span>
                </h3>
                <button
                  onClick={() => deleteFolder(f.id)}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-destructive"
                  title="Supprimer le dossier (les articles repassent en « À lire »)"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Supprimer
                </button>
              </div>
              {f.articles.length > 0 ? (
                f.articles.map((a) => (
                  <ArticleCard
                    key={a.id}
                    article={{ ...a, saved: true }}
                    loggedIn
                    onChanged={load}
                  />
                ))
              ) : (
                <p className="text-sm text-muted-foreground">Dossier vide.</p>
              )}
            </section>
          ))}
        </>
      ) : null}
    </div>
  );
}
