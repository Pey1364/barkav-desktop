import type { CapacitorConfig } from "@capacitor/cli";

// The Android app is the same web app (dist/), wrapped by Capacitor.
// androidScheme "https" keeps the app on a secure origin, as the browser version is.
const config: CapacitorConfig = {
  appId: "ir.barkav.field",
  appName: "BARKAV Field",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
};

export default config;
