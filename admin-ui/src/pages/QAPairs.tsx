import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { ru } from "date-fns/locale";
import { getQAPairs } from "@/api/endpoints";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { PlatformBadge } from "@/components/ui/PlatformBadge";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { SourceList } from "@/components/ui/SourceList";

const PLATFORM_OPTIONS = [
  { value: "", label: "Все платформы" },
  { value: "telegram", label: "Telegram" },
  { value: "vk", label: "ВКонтакте" },
  { value: "max", label: "MAX" },
];

const PAGE_SIZE = 20;

export function QAPairsPage() {
  const [page, setPage] = useState(1);
  const [platform, setPlatform] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["qa-pairs", page, platform, search],
    queryFn: () =>
      getQAPairs({
        page,
        size: PAGE_SIZE,
        platform: platform || undefined,
        search: search || undefined,
      }),
  });

  return (
    <div className="p-8">
      <PageHeader
        title="Вопросы и ответы"
        description="История диалогов пользователей с ботом"
      />

      <div className="flex items-center gap-2 mb-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(searchInput);
            setPage(1);
          }}
          className="flex items-center gap-2"
        >
          <Input
            placeholder="Поиск по тексту…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-80"
          />
        </form>
        <Select
          value={platform}
          onChange={(e) => {
            setPlatform(e.target.value);
            setPage(1);
          }}
          options={PLATFORM_OPTIONS}
        />
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-utmn-muted">Загрузка…</div>
        ) : !data?.items.length ? (
          <div className="p-8 text-center text-utmn-muted">Ничего не найдено</div>
        ) : (
          <div className="divide-y divide-utmn-border">
            {data.items.map((pair) => (
              <div key={pair.question_id} className="p-5 hover:bg-utmn-surface/50">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-xs text-utmn-muted">
                    <PlatformBadge platform={pair.platform} />
                    {pair.username && <span>@{pair.username}</span>}
                    <span>
                      {format(parseISO(pair.asked_at), "d MMM yyyy, HH:mm", {
                        locale: ru,
                      })}
                    </span>
                    {pair.model_used && (
                      <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                        {pair.model_used}
                      </span>
                    )}
                  </div>
                </div>
                <div className="space-y-2">
                  <div>
                    <div className="text-xs font-semibold text-utmn-primary mb-1">
                      Вопрос
                    </div>
                    <div className="text-sm text-slate-800 whitespace-pre-wrap">
                      {pair.question}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-utmn-accent mb-1">
                      Ответ
                    </div>
                    <div className="text-sm text-slate-700 whitespace-pre-wrap">
                      {pair.answer ?? (
                        <span className="italic text-utmn-muted">нет ответа</span>
                      )}
                    </div>
                    <SourceList sources={pair.sources} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {data && (
        <Pagination
          page={page}
          size={PAGE_SIZE}
          total={data.meta.total}
          onChange={setPage}
        />
      )}
    </div>
  );
}
