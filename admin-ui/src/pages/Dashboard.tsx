import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarCheck, MessageSquare, ShieldAlert, TrendingUp, Users } from "lucide-react";
import { getOverview, getTimeseries } from "@/api/endpoints";
import type { Period } from "@/api/types";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { PlatformDonut } from "@/components/dashboard/PlatformDonut";
import { TimeseriesChart } from "@/components/dashboard/TimeseriesChart";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";

const PERIOD_OPTIONS = [
  { value: "day", label: "По дням" },
  { value: "week", label: "По неделям" },
  { value: "month", label: "По месяцам" },
  { value: "year", label: "По годам" },
];

const PLATFORM_OPTIONS = [
  { value: "", label: "Все платформы" },
  { value: "telegram", label: "Telegram" },
  { value: "vk", label: "ВКонтакте" },
  { value: "max", label: "MAX" },
];

export function DashboardPage() {
  const [period, setPeriod] = useState<Period>("day");
  const [platform, setPlatform] = useState<string>("");

  const overviewQuery = useQuery({
    queryKey: ["overview"],
    queryFn: getOverview,
  });

  const timeseriesQuery = useQuery({
    queryKey: ["timeseries", period, platform],
    queryFn: () => getTimeseries({ period, platform: platform || undefined }),
  });

  const overview = overviewQuery.data;

  return (
    <div className="p-8">
      <PageHeader
        title="Дашборд"
        description="Общая статистика работы Вопрошалыча"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-4">
        <MetricCard
          title="Всего пользователей"
          value={overview?.users_total}
          icon={Users}
          loading={overviewQuery.isLoading}
        />
        <MetricCard
          title="Активных за 30 дней"
          value={overview?.active_users_last_month}
          icon={TrendingUp}
          loading={overviewQuery.isLoading}
        />
        <MetricCard
          title="Вопросов за 30 дней"
          value={overview?.questions_last_month}
          icon={MessageSquare}
          loading={overviewQuery.isLoading}
        />
        <MetricCard
          title="Вопросов сегодня"
          value={overview?.questions_today}
          icon={CalendarCheck}
          loading={overviewQuery.isLoading}
        />
        <MetricCard
          title="Неотвеченных"
          value={overview?.unanswered_questions_total}
          icon={AlertTriangle}
          loading={overviewQuery.isLoading}
          tone="danger"
          hint="нет информации в БЗ"
        />
        <MetricCard
          title="Нет в Confluence"
          value={overview?.not_confluence_questions_total}
          icon={ShieldAlert}
          loading={overviewQuery.isLoading}
          tone="warning"
          hint="источник utmn/sveden"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mt-4">
        <div className="xl:col-span-2">
          <div className="flex items-center gap-2 mb-2">
            <Select
              value={period}
              onChange={(e) => setPeriod(e.target.value as Period)}
              options={PERIOD_OPTIONS}
            />
            <Select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              options={PLATFORM_OPTIONS}
            />
          </div>
          <TimeseriesChart
            points={timeseriesQuery.data?.points ?? []}
            period={period}
            loading={timeseriesQuery.isLoading}
          />
        </div>
        <PlatformDonut
          data={overview?.users_by_platform ?? []}
          loading={overviewQuery.isLoading}
        />
      </div>
    </div>
  );
}
