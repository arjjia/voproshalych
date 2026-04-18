import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { ru } from "date-fns/locale";
import { getUsers } from "@/api/endpoints";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { PlatformBadge } from "@/components/ui/PlatformBadge";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { formatNumber } from "@/lib/utils";

const PLATFORM_OPTIONS = [
  { value: "", label: "Все платформы" },
  { value: "telegram", label: "Telegram" },
  { value: "vk", label: "ВКонтакте" },
  { value: "max", label: "MAX" },
];

const PAGE_SIZE = 25;

function displayName(u: {
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  platform_user_id: string;
}): string {
  const parts = [u.first_name, u.last_name].filter(Boolean).join(" ");
  if (parts) return parts;
  if (u.username) return `@${u.username}`;
  return u.platform_user_id;
}

export function UsersPage() {
  const [page, setPage] = useState(1);
  const [platform, setPlatform] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["users", page, platform, search],
    queryFn: () =>
      getUsers({
        page,
        size: PAGE_SIZE,
        platform: platform || undefined,
        search: search || undefined,
      }),
  });

  return (
    <div className="p-8">
      <PageHeader
        title="Пользователи"
        description="Все пользователи, когда-либо обращавшиеся к Вопрошалычу"
      />

      <div className="flex items-center gap-2 mb-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(searchInput);
            setPage(1);
          }}
        >
          <Input
            placeholder="Поиск по имени или username…"
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
        <table className="w-full text-sm">
          <thead className="bg-utmn-surface text-xs uppercase text-utmn-muted">
            <tr>
              <th className="text-left font-medium px-4 py-3">Пользователь</th>
              <th className="text-left font-medium px-4 py-3">Платформа</th>
              <th className="text-right font-medium px-4 py-3">Вопросов</th>
              <th className="text-left font-medium px-4 py-3">Последняя активность</th>
              <th className="text-left font-medium px-4 py-3">Зарегистрирован</th>
              <th className="text-left font-medium px-4 py-3">Рассылка</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-utmn-border">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-utmn-muted">
                  Загрузка…
                </td>
              </tr>
            ) : !data?.items.length ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-utmn-muted">
                  Ничего не найдено
                </td>
              </tr>
            ) : (
              data.items.map((u) => (
                <tr key={u.id} className="hover:bg-utmn-surface/50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{displayName(u)}</div>
                    {u.username && (
                      <div className="text-xs text-utmn-muted">@{u.username}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <PlatformBadge platform={u.platform} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatNumber(u.questions_count)}
                  </td>
                  <td className="px-4 py-3 text-utmn-muted">
                    {u.last_active_at
                      ? format(parseISO(u.last_active_at), "d MMM yyyy, HH:mm", {
                          locale: ru,
                        })
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-utmn-muted">
                    {u.created_at
                      ? format(parseISO(u.created_at), "d MMM yyyy", { locale: ru })
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {u.is_subscribed ? (
                      <span className="text-emerald-600 text-xs font-medium">Подписан</span>
                    ) : (
                      <span className="text-utmn-muted text-xs">нет</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
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
