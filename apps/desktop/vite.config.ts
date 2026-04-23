import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Electron packaged builds load the renderer from file://. Using a relative base keeps
  // JS/CSS asset URLs working (instead of pointing at /assets/* which doesn't exist).
  base: "./",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
  build: {
    outDir: "dist",
  },
});
