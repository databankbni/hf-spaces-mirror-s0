import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        spotify: {
          green: "#1db954",
          black: "#0a0a0a",
          panel: "#111111",
          card: "#1a1a1a",
          border: "#222222",
          text: "#ffffff",
          muted: "#aaaaaa",
        },
        source: {
          play_store: "#1db954",
          reddit: "#ff6314",
          spotify_community: "#5865f2",
          trustpilot: "#00b67a",
          youtube: "#ff0000",
          app_store: "#007aff",
        },
      },
    },
  },
  plugins: [],
};

export default config;
