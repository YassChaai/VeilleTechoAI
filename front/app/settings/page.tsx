"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";

export default function SettingsPage() {
  const [keywords, setKeywords] = useState("");
  const [hideRead, setHideRead] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setKeywords(s.keywords);
        setHideRead(s.hide_read);
        setLoggedIn(s.logged_in);
      })
      .finally(() => setLoading(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setSaved(false);
    try {
      await api.saveSettings(keywords, hideRead);
      setSaved(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="mb-1 text-[22px] font-bold tracking-tight">Réglages</h2>
      <p className="mb-6 text-[13px] text-muted-foreground">
        Personnalise le classement des articles. Les mots-clés remontent les sujets qui
        t&apos;intéressent en haut de la liste.
      </p>

      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : (
        <form onSubmit={submit} className="space-y-6">
          <div className="grid gap-2">
            <Label htmlFor="keywords">Mots-clés prioritaires (séparés par des virgules)</Label>
            <Textarea
              id="keywords"
              rows={3}
              placeholder="ia, cybersécurité, startup, design system…"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
            />
          </div>

          {loggedIn && (
            <div className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
              <div>
                <Label className="text-foreground">Masquer les articles lus par défaut</Label>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  La liste s&apos;ouvre sur « Non lus » (les lus ne sont jamais mis en avant).
                </p>
              </div>
              <Switch checked={hideRead} onCheckedChange={setHideRead} />
            </div>
          )}

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy}>
              Enregistrer
            </Button>
            {saved && <span className="text-sm text-primary">Préférences enregistrées ✓</span>}
          </div>

          {!loggedIn && (
            <p className="text-[13px] text-muted-foreground">
              Ces réglages s&apos;appliquent au profil invité. Connecte-toi pour des préférences
              par compte + le suivi lu/non-lu.
            </p>
          )}
        </form>
      )}
    </div>
  );
}
