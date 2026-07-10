"use client";

import { useEffect, useState } from "react";

// Easter egg 🌴 — clic sur le logo = « mode hallucination » (couleurs + tailles
// en mouvement continu + reggae). Re-clic = arrêt. Aucun impact hors de ce clic.
const VIDEO_ID = "1ti2YCFgCoI"; // Bob Marley

export function TripLogo() {
  const [trip, setTrip] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("trip", trip);
    return () => root.classList.remove("trip");
  }, [trip]);

  return (
    <>
      <button
        type="button"
        onClick={() => setTrip((v) => !v)}
        aria-pressed={trip}
        aria-label={trip ? "Arrêter le mode hallucination" : "Le Guetteur — accueil"}
        title={trip ? "Re-clique pour revenir sur Terre 🌍" : "Le Guetteur"}
        className="flex items-center gap-3 rounded-pill hover:no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="" className="block h-10 w-auto" />
        <span className="text-[18px] font-bold tracking-[0.04em] text-foreground">Le Guetteur</span>
      </button>

      {trip && (
        // Rendu hors écran mais présent → l'audio joue (clic = geste utilisateur
        // ⇒ autoplay autorisé). Démonter l'iframe coupe la musique.
        <iframe
          title="Reggae"
          aria-hidden
          src={`https://www.youtube.com/embed/${VIDEO_ID}?autoplay=1&loop=1&playlist=${VIDEO_ID}&controls=0`}
          allow="autoplay"
          className="pointer-events-none fixed left-[-10000px] top-0 h-[200px] w-[356px] border-0"
        />
      )}
    </>
  );
}
