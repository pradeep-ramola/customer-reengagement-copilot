import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172026",
        mist: "#f6f8f7",
        line: "#d8e0dd",
        teal: "#0f766e",
        amber: "#b7791f",
        rose: "#be123c",
        cobalt: "#3156a3"
      },
      boxShadow: {
        soft: "0 10px 30px rgba(23, 32, 38, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
