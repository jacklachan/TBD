import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Every API prefix the app calls. A route missing here works in the built
    // app, which is served from the same origin, and fails only under
    // `npm run dev` -- so it is worth keeping in step with backend/security.py's
    // own prefix list rather than discovering the gap in a browser.
    proxy: Object.fromEntries(
      ["/cases", "/runs", "/context", "/health", "/ingest", "/interop"].map(
        (path) => [path, "http://127.0.0.1:8000"],
      ),
    ),
  },
  test: { include: ["src/**/*.test.ts"] },
});
