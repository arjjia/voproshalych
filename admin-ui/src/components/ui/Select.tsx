import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface Option {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: Option[];
  placeholder?: string;
}

export function Select({ options, placeholder, className, ...props }: SelectProps) {
  return (
    <select
      {...props}
      className={cn(
        "h-9 rounded-lg border border-utmn-border bg-white px-3 text-sm",
        "focus:outline-none focus:ring-2 focus:ring-utmn-primary/40 focus:border-utmn-primary",
        className,
      )}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
