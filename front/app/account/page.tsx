"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, type AccountResponse } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { frDate } from "@/lib/utils";

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-2xl font-bold leading-none text-primary">{n}</span>
      <span className="mt-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
    </div>
  );
}

export default function AccountPage() {
  const { user, loading: sessionLoading, setUser } = useSession();
  const router = useRouter();

  const [data, setData] = useState<AccountResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pwdMsg, setPwdMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.account());
    } catch {
      /* garde ci-dessous */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!sessionLoading && user) load();
    else if (!sessionLoading) setLoading(false);
  }, [sessionLoading, user, load]);

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setPwdMsg(null);
    try {
      await api.changePassword(current, next, confirm);
      setPwdMsg({ ok: true, text: "Mot de passe mis à jour ✓" });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setPwdMsg({ ok: false, text: err instanceof ApiError ? err.message : "Erreur" });
    } finally {
      setBusy(false);
    }
  }

  async function deleteAccount() {
    await api.deleteAccount();
    setUser(null);
    router.push("/");
  }

  if (!sessionLoading && !user) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card p-12 text-center text-muted-foreground">
        <p>Connecte-toi pour gérer ton compte.</p>
        <Link href="/login" className="mt-3 inline-block">
          Se connecter
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <h2 className="mb-6 text-[22px] font-bold tracking-tight">Mon compte</h2>

      {loading || !data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <Card className="mb-8 p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-mono text-lg font-semibold">{data.user.username}</span>
              <span className="text-xs text-muted-foreground">
                membre depuis {frDate(data.user.created_at)}
              </span>
            </div>
            <div className="mt-4 flex gap-8">
              <Stat n={data.stats.read} label="lus" />
              <Stat n={data.stats.saved} label="enregistrés" />
              <Stat n={data.stats.folders} label="dossiers" />
            </div>
          </Card>

          <section className="mb-8">
            <h3 className="mb-3 border-b border-border pb-2 text-[15px] font-semibold">
              Changer le mot de passe
            </h3>
            <form onSubmit={changePassword} className="grid max-w-sm gap-4">
              <div className="grid gap-2">
                <Label htmlFor="current">Mot de passe actuel</Label>
                <Input
                  id="current"
                  type="password"
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="new">Nouveau mot de passe (min. 6)</Label>
                <Input
                  id="new"
                  type="password"
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="confirm">Confirmer</Label>
                <Input
                  id="confirm"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                />
              </div>
              <div className="flex items-center gap-3">
                <Button type="submit" disabled={busy}>
                  Mettre à jour
                </Button>
                {pwdMsg && (
                  <span className={pwdMsg.ok ? "text-sm text-primary" : "text-sm text-destructive"}>
                    {pwdMsg.text}
                  </span>
                )}
              </div>
            </form>
          </section>

          <section>
            <h3 className="mb-3 border-b border-border pb-2 text-[15px] font-semibold text-destructive">
              Zone de danger
            </h3>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="destructive">Supprimer mon compte</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Supprimer définitivement le compte ?</DialogTitle>
                  <DialogDescription>
                    Cette action est irréversible : préférences, lectures, dossiers et articles
                    enregistrés seront supprimés. La navigation reste possible sans compte.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="destructive" onClick={deleteAccount}>
                    Oui, supprimer
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </section>
        </>
      )}
    </div>
  );
}
