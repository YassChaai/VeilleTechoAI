import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "@/components/session-provider";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = {
  title: "Le Guetteur",
  description:
    "Veille technologique auto-alimentée — Tech, Business de la tech, Data & IA, UX. Ingestion, déduplication, vulgarisation FR et dashboard filtrable.",
  icons: { icon: "/logo.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="flex min-h-screen flex-col bg-background text-foreground">
        <SessionProvider>
          <SiteHeader />
          <main className="mx-auto w-full max-w-[900px] flex-1 px-5 pb-14 pt-7">{children}</main>
          <SiteFooter />
        </SessionProvider>
      </body>
    </html>
  );
}
