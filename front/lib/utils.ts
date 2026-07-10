import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Slug de domaine → classe de chip color-codée. */
export function chipClass(slug: string | null | undefined): string {
  switch (slug) {
    case "tech":
      return "chip-tech";
    case "business":
      return "chip-business";
    case "data":
      return "chip-data";
    case "ux":
      return "chip-ux";
    default:
      return "chip-none";
  }
}

/** Date ISO → JJ/MM/AAAA (locale FR), silencieux si vide/invalide. */
export function frDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}
