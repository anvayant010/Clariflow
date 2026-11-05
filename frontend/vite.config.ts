import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev: the browser talks to Vite (5173); /api is forwarded to the FastAPI server (8000).
// Production: `npm run build` writes frontend/dist, which FastAPI serves from the same origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "jsdom", clearMocks: true },
});
