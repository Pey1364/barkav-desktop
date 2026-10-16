import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the same build works from GitHub Pages or a local folder.
export default defineConfig({
  base: "./",
  plugins: [react()],
});
