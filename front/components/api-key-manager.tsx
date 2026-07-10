"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Gestion BYOK de la clé Claude du compte (utilisée dans Réglages). Ne montre jamais
// la clé complète : le back ne renvoie qu'un indice masqué (`hint`).
export function ApiKeyManager({
  hasKey,
  hint,
  onChanged,
}: {
  hasKey: boolean;
  hint: string | null;
  onChanged: () => void | Promise<void>;
}) {
  const [apiKey, setApiKey] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.setApiKey(apiKey.trim());
      setApiKey("");
      setMsg({ ok: true, text: "Clé enregistrée ✓" });
      await onChanged();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Erreur" });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setMsg(null);
    try {
      await api.removeApiKey();
      setMsg({ ok: true, text: "Clé retirée." });
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="mb-3 text-[13px] text-muted-foreground">
        Ta propre clé Claude sert à résumer et traduire les articles quand <em>tu</em> lances
        « Chercher de nouveaux articles ». Sans clé, le mode dégradé (extractif) prend le relais.
        Utilise de préférence une clé dédiée et révocable — elle est stockée côté serveur et
        n&apos;est jamais réaffichée en entier.
      </p>
      {hasKey ? (
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-pill bg-secondary px-3 py-1 font-mono text-xs">
            clé active · {hint}
          </span>
          <Button variant="outline" size="sm" onClick={remove} disabled={busy}>
            Retirer
          </Button>
          {msg && (
            <span className={msg.ok ? "text-sm text-primary" : "text-sm text-destructive"}>
              {msg.text}
            </span>
          )}
        </div>
      ) : (
        <form onSubmit={save} className="grid max-w-sm gap-3">
          <div className="grid gap-2">
            <Label htmlFor="apikey">Clé (sk-ant-…)</Label>
            <Input
              id="apikey"
              type="password"
              placeholder="sk-ant-..."
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy || !apiKey.trim()}>
              Enregistrer la clé
            </Button>
            {msg && (
              <span className={msg.ok ? "text-sm text-primary" : "text-sm text-destructive"}>
                {msg.text}
              </span>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
