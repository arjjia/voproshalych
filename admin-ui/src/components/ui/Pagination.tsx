import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn, formatNumber } from "@/lib/utils";

interface Props {
  page: number;
  size: number;
  total: number;
  onChange: (page: number) => void;
}

export function Pagination({ page, size, total, onChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / size));
  const from = total === 0 ? 0 : (page - 1) * size + 1;
  const to = Math.min(total, page * size);

  return (
    <div className="flex items-center justify-between py-3 text-sm">
      <div className="text-utmn-muted">
        Показано {formatNumber(from)}–{formatNumber(to)} из {formatNumber(total)}
      </div>
      <div className="flex items-center gap-2">
        <button
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className={cn(
            "w-8 h-8 rounded-lg border border-utmn-border flex items-center justify-center",
            "disabled:opacity-40 hover:bg-utmn-surface",
          )}
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="tabular-nums">
          {page} / {totalPages}
        </span>
        <button
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
          className={cn(
            "w-8 h-8 rounded-lg border border-utmn-border flex items-center justify-center",
            "disabled:opacity-40 hover:bg-utmn-surface",
          )}
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
