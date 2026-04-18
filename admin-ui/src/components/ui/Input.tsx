import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-9 rounded-lg border border-utmn-border bg-white px-3 text-sm",
        "focus:outline-none focus:ring-2 focus:ring-utmn-primary/40 focus:border-utmn-primary",
        "placeholder:text-utmn-muted",
        className,
      )}
    />
  );
}
