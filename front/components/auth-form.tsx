"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useSession } from "./session-provider";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Button } from "./ui/button";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { setUser } = useSession();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isRegister = mode === "register";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = isRegister
        ? await api.register(username, password, confirm)
        : await api.login(username, password);
      setUser(res.user);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm py-6">
      <h2 className="mb-1 text-center text-[22px] font-bold tracking-tight">
        {isRegister ? "Créer un compte" : "Connexion"}
      </h2>
      <p className="mb-6 text-center text-[13px] text-muted-foreground">
        {isRegister
          ? "Suis tes lectures et enregistre des articles par dossier."
          : "Ravi de te revoir sur Le Guetteur."}
      </p>

      <Card className="p-6">
        <form onSubmit={submit} className="grid gap-4">
          {error && (
            <p className="tint-destructive rounded-md border px-3 py-2 text-[13.5px] text-destructive">
              {error}
            </p>
          )}
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
              autoComplete={isRegister ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
            />
          </div>
          {isRegister && (
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
          )}
          <Button type="submit" disabled={busy} className="mt-1">
            {isRegister ? "Créer mon compte" : "Se connecter"}
          </Button>
        </form>
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
