import type { LucideIcon } from "lucide-react";
import { formatNumber } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: number | undefined;
  hint?: string;
  icon: LucideIcon;
  loading?: boolean;
}

export function MetricCard({ title, value, hint, icon: Icon, loading }: MetricCardProps) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm text-utmn-muted">{title}</div>
        <div className="w-9 h-9 rounded-lg bg-utmn-primary/10 flex items-center justify-center text-utmn-primary">
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold text-utmn-dark tabular-nums">
        {loading ? "—" : value !== undefined ? formatNumber(value) : "—"}
      </div>
      {hint && <div className="mt-1 text-xs text-utmn-muted">{hint}</div>}
    </div>
  );
}
