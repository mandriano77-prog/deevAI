import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // deevAI brand palette — neutral-leaning with a single accent
        ink: {
          50: "#f6f6f5",
          100: "#e7e7e4",
          200: "#c9c9c4",
          400: "#86857f",
          600: "#4a4a46",
          800: "#252523",
          900: "#0e0e0c",
        },
        accent: {
          // Riverbed teal — deevAI brand
          50: "#e3f5ee",
          100: "#bce8d8",
          400: "#3aa882",
          600: "#178060",
          700: "#0e6049",
          900: "#06342a",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      letterSpacing: {
        tightest: "-0.04em",
      },
    },
  },
  plugins: [],
};

export default config;
