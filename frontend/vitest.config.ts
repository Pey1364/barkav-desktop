import { defineConfig } from "vitest/config";

// scrypt (N=32768) takes a moment per envelope, so tests get more time than the default 5 seconds.
export default defineConfig({
  test: {
    testTimeout: 60_000,
    hookTimeout: 60_000,
  },
});
