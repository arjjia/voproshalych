import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const PLATFORM_LABELS: Record<string, string> = {
  telegram: "Telegram",
  vk: "ВКонтакте",
  max: "MAX",
};

export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n);
}

export interface SourceKind {
  label: string;
  color: string;
}

export function detectSourceKind(url: string | null): SourceKind {
  if (!url) return { label: "Документ", color: "bg-slate-100 text-slate-700" };
  const u = url.toLowerCase();
  if (u.includes("confluence") || u.includes("help.utmn"))
    return { label: "Confluence", color: "bg-indigo-50 text-indigo-700" };
  if (u.includes("sveden"))
    return { label: "Сведения об ОО", color: "bg-amber-50 text-amber-700" };
  if (u.includes("utmn.ru") || u.includes("utmn.edu"))
    return { label: "Сайт ТюмГУ", color: "bg-utmn-primary/10 text-utmn-primary" };
  if (u.endsWith(".pdf"))
    return { label: "PDF", color: "bg-rose-50 text-rose-700" };
  return { label: "Документ", color: "bg-slate-100 text-slate-700" };
}
