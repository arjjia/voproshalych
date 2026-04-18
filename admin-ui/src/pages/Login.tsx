import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/Input";
import { saveCredentials } from "@/lib/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md card p-6">
        <div className="flex items-center gap-3 mb-6">
          <img src="/utmn-logo.png" alt="ТюмГУ" className="w-10 h-10 object-contain" />
          <div>
            <div className="font-semibold text-sm leading-tight">ТюмГУ</div>
            <div className="text-xs text-utmn-muted leading-tight">Вопрошалыч · Admin</div>
          </div>
        </div>

        <h1 className="text-lg font-semibold mb-1">Вход в админ-панель</h1>
        <p className="text-sm text-utmn-muted mb-4">
          Введите логин и пароль для доступа к аналитике.
        </p>

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            saveCredentials({ username, password });
            navigate("/", { replace: true });
          }}
        >
          <Input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Логин"
            autoComplete="username"
            className="w-full"
            required
          />
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Пароль"
            autoComplete="current-password"
            className="w-full"
            required
          />
          <button
            type="submit"
            className="w-full h-9 rounded-lg bg-utmn-primary text-white text-sm font-medium hover:opacity-95 transition-opacity"
          >
            Войти
          </button>
        </form>
      </div>
    </div>
  );
}
