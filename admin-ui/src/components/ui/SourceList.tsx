import { ExternalLink, FileText } from "lucide-react";
import type { Source } from "@/api/types";
import { cn, detectSourceKind } from "@/lib/utils";

interface Props {
  sources: Source[];
}

export function SourceList({ sources }: Props) {
  if (!sources.length) return null;

  return (
    <div className="mt-3 pt-3 border-t border-utmn-border">
      <div className="text-xs font-semibold text-utmn-muted mb-2">
        Источники ({sources.length})
      </div>
      <div className="flex flex-wrap gap-2">
        {sources.map((s, i) => {
          const kind = detectSourceKind(s.url);
          const isUrl = s.url?.startsWith("http");
          const title = s.title ?? s.url ?? s.id ?? "Документ";
          const content = (
            <>
              <span
                className={cn(
                  "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0",
                  kind.color,
                )}
              >
                {kind.label}
              </span>
              <span className="truncate max-w-[28rem]">{title}</span>
              {isUrl && <ExternalLink className="w-3 h-3 shrink-0 opacity-60" />}
              {!isUrl && <FileText className="w-3 h-3 shrink-0 opacity-60" />}
            </>
          );

          return isUrl ? (
            <a
              key={s.id ?? i}
              href={s.url!}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md bg-utmn-surface border border-utmn-border hover:border-utmn-primary/50 hover:bg-utmn-primary/5 transition-colors"
            >
              {content}
            </a>
          ) : (
            <span
              key={s.id ?? i}
              className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md bg-utmn-surface border border-utmn-border"
              title={s.url ?? undefined}
            >
              {content}
            </span>
          );
        })}
      </div>
    </div>
  );
}
