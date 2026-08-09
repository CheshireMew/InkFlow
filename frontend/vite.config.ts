import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

const versionSource = readFileSync(new URL("../src/inkflow/__about__.py", import.meta.url), "utf8");
const version = versionSource.match(/__version__\s*=\s*["']([^"']+)["']/)?.[1];
if (!version) throw new Error("InkFlow version source is invalid");

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: { __INKFLOW_VERSION__: JSON.stringify(version) },
  server: {
    proxy: {
      "/api": "http://localhost:8765",
    },
  },
});
