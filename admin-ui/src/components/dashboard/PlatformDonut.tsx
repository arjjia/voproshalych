import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { PlatformCount } from "@/api/types";
import { formatNumber, platformLabel } from "@/lib/utils";

interface Props {
  data: PlatformCount[];
  loading?: boolean;
}

const COLORS: Record<string, string> = {
  telegram: "#2AABEE",
  vk: "#0077FF",
  max: "#F26B1A",
};

function colorFor(platform: string): string {
  return COLORS[platform] ?? "#6B7280";
}

export function PlatformDonut({ data, loading }: Props) {
  const chartData = data.map((d) => ({
    name: platformLabel(d.platform),
    value: d.count,
    color: colorFor(d.platform),
  }));
  const total = chartData.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="card p-5">
      <h2 className="text-sm font-semibold text-utmn-dark mb-4">Пользователи по платформам</h2>
      {loading ? (
        <div className="h-64 flex items-center justify-center text-sm text-utmn-muted">
          Загрузка…
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-sm text-utmn-muted">
          Нет данных
        </div>
      ) : (
        <div className="flex items-center gap-6">
          <div className="w-48 h-48 relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={2}
                >
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    borderRadius: 8,
                    border: "1px solid #E3E8EF",
                    fontSize: 13,
                  }}
                  formatter={(value: number) => [formatNumber(value), "пользователей"]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <div className="text-2xl font-semibold text-utmn-dark tabular-nums">
                {formatNumber(total)}
              </div>
              <div className="text-xs text-utmn-muted">всего</div>
            </div>
          </div>
          <div className="flex-1 space-y-2">
            {chartData.map((d) => (
              <div key={d.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: d.color }}
                  />
                  <span className="text-slate-700">{d.name}</span>
                </div>
                <div className="font-medium tabular-nums">
                  {formatNumber(d.value)}
                  <span className="text-utmn-muted ml-2 text-xs">
                    {total > 0 ? ((d.value / total) * 100).toFixed(0) : 0}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
