"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "./session-provider";

// Accès réservé : sans compte, on redirige vers l'inscription (login/register libres).
const PUBLIC = ["/login", "/register"];

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC.includes(pathname);

  useEffect(() => {
    if (!loading && !user && !isPublic) router.replace("/register");
  }, [loading, user, isPublic, router]);

  if (loading) {
    return (
      <div className="py-24 text-center text-sm text-muted-foreground">Chargement…</div>
    );
  }
  if (!user && !isPublic) return null; // en cours de redirection vers /register
  return <>{children}</>;
}
