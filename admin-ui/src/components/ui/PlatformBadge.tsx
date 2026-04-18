import { cn, platformLabel } from "@/lib/utils";

const STYLES: Record<string, string> = {
  telegram: "bg-[#2AABEE]/10 text-[#2AABEE]",
  vk: "bg-[#0077FF]/10 text-[#0077FF]",
  max: "bg-[#F26B1A]/10 text-[#F26B1A]",
};

export function PlatformBadge({ platform }: { platform: string | null }) {
  if (!platform) return <span className="text-utmn-muted text-xs">—</span>;
  const cls = STYLES[platform] ?? "bg-slate-100 text-slate-600";
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
        cls,
      )}
    >
      {platformLabel(platform)}
    </span>
  );
}
