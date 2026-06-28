import type { LucideIcon } from "lucide-react";
import { formatNumber } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: number | undefined;
  hint?: string;
  icon: LucideIcon;
  loading?: boolean;
  tone?: "default" | "danger" | "warning";
}

export function MetricCard({
  title,
  value,
  hint,
  icon: Icon,
  loading,
  tone = "default",
}: MetricCardProps) {
  const isDanger = tone === "danger";
  const isWarning = tone === "warning";

  return (
    <div
      className={cn(
        "card p-5",
        isDanger && "border-red-200 bg-red-50/50",
        isWarning && "border-amber-200 bg-amber-50/60",
      )}
    >
      <div className="flex items-center justify-between">
        <div
          className={cn(
            "text-sm",
            isDanger && "text-red-700",
            isWarning && "text-amber-800",
            !isDanger && !isWarning && "text-utmn-muted",
          )}
        >
          {title}
        </div>
        <div
          className={cn(
            "w-9 h-9 rounded-lg flex items-center justify-center",
            isDanger && "bg-red-100 text-red-700",
            isWarning && "bg-amber-100 text-amber-800",
            !isDanger && !isWarning && "bg-utmn-primary/10 text-utmn-primary",
          )}
        >
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div
        className={cn(
          "mt-3 text-3xl font-semibold tabular-nums",
          isDanger && "text-red-800",
          isWarning && "text-amber-900",
          !isDanger && !isWarning && "text-utmn-dark",
        )}
      >
        {loading ? "—" : value !== undefined ? formatNumber(value) : "—"}
      </div>
      {hint && <div className="mt-1 text-xs text-utmn-muted">{hint}</div>}
    </div>
  );
}
