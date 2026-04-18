import { NavLink, Outlet } from "react-router-dom";
import { BarChart3, LogOut, MessageSquare, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { clearCredentials } from "@/lib/auth";

const NAV = [
  { to: "/", label: "Дашборд", icon: BarChart3 },
  { to: "/qa", label: "Вопросы и ответы", icon: MessageSquare },
  { to: "/users", label: "Пользователи", icon: Users },
];

export function AppLayout() {
  return (
    <div className="flex min-h-screen">
      <aside className="w-64 bg-white border-r border-utmn-border flex flex-col">
        <div className="px-6 py-5 flex items-center gap-3 border-b border-utmn-border">
          <img src="/utmn-logo.png" alt="ТюмГУ" className="w-10 h-10 object-contain" />
          <div>
            <div className="font-semibold text-sm leading-tight">ТюмГУ</div>
            <div className="text-xs text-utmn-muted leading-tight">Вопрошалыч</div>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-utmn-primary text-white"
                    : "text-slate-700 hover:bg-utmn-surface",
                )
              }
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-utmn-border space-y-3">
          <button
            type="button"
            onClick={clearCredentials}
            className="w-full h-9 px-3 rounded-lg border border-utmn-border text-slate-700 text-sm font-medium flex items-center justify-center gap-2 hover:bg-utmn-surface transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Выйти
          </button>
          <div className="text-xs text-utmn-muted">
            Админ-панель · только для внутренней сети ТюмГУ
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
