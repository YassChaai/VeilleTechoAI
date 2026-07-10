"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, type AiStatus } from "@/lib/api";
import { useSession } from "./session-provider";
import { cn } from "@/lib/utils";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { setUser } = useSession();
  const isRegister = mode === "register";

  const [step, setStep] = useState(1);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [aiMode, setAiMode] = useState<"claude" | "free">("claude");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Modèles Claude proposés à l'étape 2.
  useEffect(() => {
    if (!isRegister) return;
    api
      .aiStatus()
      .then((s) => {
        setAi(s);
        if (s.models.length) setModel(s.models[0].id);
      })
      .catch(() => {});
  }, [isRegister]);

  function goStep2(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (username.trim().length < 3)
      return setError("Le nom d'utilisateur doit faire au moins 3 caractères.");
    if (password.length < 6)
      return setError("Le mot de passe doit faire au moins 6 caractères.");
    if (password !== confirm)
      return setError("Les deux mots de passe ne correspondent pas.");
    setStep(2);
  }

  async function createAccount() {
    setBusy(true);
    setError(null);
    try {
      const useClaude = aiMode === "claude";
      const res = await api.register(
        username,
        password,
        confirm,
        useClaude ? apiKey.trim() : "",
        useClaude ? model : "",
      );
      setUser(res.user);
      // À la création, on lance directement la première récupération d'articles
      // (avec le mode d'IA choisi). La progression s'affiche sur la page d'accueil.
      await api.ingestRefresh().catch(() => {});
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setBusy(false);
    }
  }

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(username, password);
      setUser(res.user);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setBusy(false);
    }
  }

  const errorBanner = error && (
    <p className="tint-destructive rounded-md border px-3 py-2 text-[13.5px] text-destructive">
      {error}
    </p>
  );

  return (
    <div className="mx-auto max-w-sm py-6">
      <h2 className="mb-1 text-center text-[22px] font-bold tracking-tight">
        {isRegister ? "Créer un compte" : "Connexion"}
      </h2>
      <p className="mb-6 text-center text-[13px] text-muted-foreground">
        {isRegister
          ? step === 1
            ? "Un compte est nécessaire pour utiliser Le Guetteur."
            : "Comment veux-tu résumer les articles ?"
          : "Ravi de te revoir sur Le Guetteur."}
      </p>

      <Card className="p-6">
        {/* --- Connexion --------------------------------------------------- */}
        {!isRegister && (
          <form onSubmit={login} className="grid gap-4">
            {errorBanner}
            <div className="grid gap-2">
              <Label htmlFor="username">Nom d&apos;utilisateur</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">Mot de passe</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={busy} className="mt-1">
              Se connecter
            </Button>
          </form>
        )}

        {/* --- Inscription étape 1 : identifiants -------------------------- */}
        {isRegister && step === 1 && (
          <form onSubmit={goStep2} className="grid gap-4">
            {errorBanner}
            <div className="grid gap-2">
              <Label htmlFor="username">Nom d&apos;utilisateur</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                minLength={3}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">Mot de passe</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="confirm">Confirmer le mot de passe</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                minLength={6}
              />
            </div>
            <Button type="submit" className="mt-1">
              Suivant
            </Button>
          </form>
        )}

        {/* --- Inscription étape 2 : mode d'IA ----------------------------- */}
        {isRegister && step === 2 && (
          <div className="grid gap-4">
            {errorBanner}

            <button
              type="button"
              onClick={() => setAiMode("claude")}
              className={cn(
                "rounded-lg border p-3 text-left transition-colors",
                aiMode === "claude" ? "border-primary tint-primary" : "border-border",
              )}
            >
              <div className="text-[14px] font-semibold">Claude (ta clé API)</div>
              <div className="text-xs text-muted-foreground">
                Résumés et titres en français, qualité maximale. Ta clé, ta facturation.
              </div>
            </button>

            {aiMode === "claude" && (
              <div className="grid gap-3 rounded-lg border border-border bg-secondary p-3">
                <div className="grid gap-2">
                  <Label htmlFor="apikey">Clé API Anthropic</Label>
                  <Input
                    id="apikey"
                    type="password"
                    autoComplete="off"
                    placeholder="sk-ant-…"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                  />
                </div>
                {ai && ai.models.length > 0 && (
                  <div className="grid gap-2">
                    <Label htmlFor="model">Modèle</Label>
                    <Select value={model} onValueChange={setModel}>
                      <SelectTrigger id="model">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ai.models.map((m) => (
                          <SelectItem key={m.id} value={m.id}>
                            {m.label} — {m.hint}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            )}

            <button
              type="button"
              onClick={() => setAiMode("free")}
              className={cn(
                "rounded-lg border p-3 text-left transition-colors",
                aiMode === "free" ? "border-primary tint-primary" : "border-border",
              )}
            >
              <div className="text-[14px] font-semibold">Gratuit, sans clé</div>
              <div className="text-xs text-muted-foreground">
                Résumés extractifs automatiques — qualité réduite, souvent en anglais.
              </div>
            </button>

            {aiMode === "free" && (
              <p className="rounded-md border border-border bg-secondary px-3 py-2 text-xs text-muted-foreground">
                ⚠️ Sans clé, les résumés et les titres restent <strong>basiques</strong> et
                souvent <strong>en anglais</strong>. Tu pourras ajouter une clé Claude plus tard
                dans <strong>Réglages</strong> pour passer au français.
              </p>
            )}

            <p className="text-[12.5px] text-muted-foreground">
              À la création, une première récupération d&apos;articles se lance directement.
              Tu pourras changer de mode plus tard dans <strong>Réglages</strong>.
            </p>

            <div className="flex items-center justify-between gap-3">
              <Button type="button" variant="outline" onClick={() => setStep(1)} disabled={busy}>
                Retour
              </Button>
              <Button
                type="button"
                onClick={createAccount}
                disabled={busy || (aiMode === "claude" && !apiKey.trim())}
              >
                {busy ? "Création…" : "Créer mon compte"}
              </Button>
            </div>
          </div>
        )}
      </Card>

      <p className="mt-4 text-center text-[13.5px] text-muted-foreground">
        {isRegister ? (
          <>
            Déjà un compte ? <Link href="/login">Se connecter</Link>
          </>
        ) : (
          <>
            Pas encore de compte ? <Link href="/register">Créer un compte</Link>
          </>
        )}
      </p>
    </div>
  );
}
