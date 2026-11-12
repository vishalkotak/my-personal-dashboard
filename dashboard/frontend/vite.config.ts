import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Everything stays on this machine: the dev server listens on 127.0.0.1 only and
// forwards /api to the local backend, so the browser never talks to anything else.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", ""); // dashboard/.env plus the real environment
  const apiPort = Number(env.API_PORT || 8000);
  const port = Number(env.FRONTEND_PORT || 5173);
  const proxy = { "/api": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: false } };
  return {
    plugins: [react()],
    envDir: "..", // dashboard/.env; only VITE_* variables would ever reach the browser (we use none)
    server: { host: "127.0.0.1", port, strictPort: true, proxy },
    preview: { host: "127.0.0.1", port, strictPort: true, proxy },
    build: { sourcemap: false, chunkSizeWarningLimit: 1200 },
  };
});
