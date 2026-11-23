import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api goes to the local attack-lab server (uvicorn api.lab:app --port 8788).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8788" } },
});
