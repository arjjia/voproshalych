import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        utmn: {
          primary: "#00AEEF",
          dark: "#0077A8",
          accent: "#F26B1A",
          surface: "#F5F7FA",
          border: "#E3E8EF",
          muted: "#6B7280",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
