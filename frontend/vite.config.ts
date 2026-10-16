import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the same build works from GitHub Pages or a local folder.
// Two pages: the phone app (index.html) and the desktop review page (desktop.html).
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        desktop: fileURLToPath(new URL("./desktop.html", import.meta.url)),
      },
    },
  },
});
