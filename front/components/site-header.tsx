"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "./session-provider";
import { api } from "@/lib/api";
import { Button } from "./ui/button";
import { TripLogo } from "./trip-logo";
import { cn } from "@/lib/utils";

const BASE_NAV = [
  { href: "/", label: "Articles" },
  { href: "/trends", label: "Tendances" },
  { href: "/digest", label: "Digest" },
  { href: "/sources", label: "Sources" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/" || pathname.startsWith("/article");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SiteHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, setUser } = useSession();

  const nav = [
    ...BASE_NAV,
    ...(user ? [{ href: "/library", label: "Bibliothèque" }] : []),
    { href: "/settings", label: "Réglages" },
    ...(user ? [{ href: "/account", label: "Mon compte" }] : []),
  ];

  async function logout() {
    try {
      await api.logout();
    } finally {
      setUser(null);
      router.push("/");
    }
  }

  return (
    <header className="sticky top-0 z-10 flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-border bg-card px-5 py-3">
      <TripLogo />

      <nav className="flex flex-wrap gap-1">
        {nav.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "rounded-pill px-3 py-1.5 text-sm font-medium hover:no-underline",
              isActive(pathname, item.href)
                ? "tint-primary text-primary"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground"
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3 text-[13.5px]">
        {user ? (
          <>
            <Link href="/account" className="font-mono font-semibold text-foreground hover:no-underline">
              {user.username}
            </Link>
            <Button variant="outline" size="sm" onClick={logout}>
              Déconnexion
            </Button>
          </>
        ) : (
          <>
            <Link href="/login" className="text-primary">
              Connexion
            </Link>
            <Button size="sm" asChild>
              <Link href="/register" className="hover:no-underline">
                Créer un compte
              </Link>
            </Button>
          </>
        )}
      </div>
    </header>
  );
}
