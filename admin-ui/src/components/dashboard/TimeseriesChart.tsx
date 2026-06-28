import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";
import { ru } from "date-fns/locale";
import type { Period, TimeseriesPoint } from "@/api/types";

interface Props {
  points: TimeseriesPoint[];
  period: Period;
  loading?: boolean;
}

const FORMATS: Record<Period, string> = {
  day: "d MMM",
  week: "d MMM",
  month: "LLL yyyy",
  year: "yyyy",
};

export function TimeseriesChart({ points, period, loading }: Props) {
  const data = points.map((p) => ({
    label: format(parseISO(p.bucket), FORMATS[period], { locale: ru }),
    count: p.count,
  }));

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-utmn-dark">Вопросы по времени</h2>
      </div>
      <div className="h-72">
        {loading ? (
          <div className="h-full flex items-center justify-center text-sm text-utmn-muted">
            Загрузка…
          </div>
        ) : data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-sm text-utmn-muted">
            Нет данных за выбранный период
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E3E8EF" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 12, fill: "#6B7280" }}
                stroke="#E3E8EF"
              />
              <YAxis
                allowDecimals={false}
                tick={{ fontSize: 12, fill: "#6B7280" }}
                stroke="#E3E8EF"
              />
              <Tooltip
                contentStyle={{
                  borderRadius: 8,
                  border: "1px solid #E3E8EF",
                  fontSize: 13,
                }}
                labelStyle={{ color: "#00335C", fontWeight: 600 }}
                formatter={(value: number) => [value, "вопросов"]}
              />
              <Bar
                dataKey="count"
                fill="#005BAA"
                radius={[6, 6, 0, 0]}
                maxBarSize={48}
                activeBar={{ fill: "#005BAA" }}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
