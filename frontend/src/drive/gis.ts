// Google sign-in in the browser (Google Identity Services, token model). The access token lives
// only in memory and lasts about an hour; a silent request renews it when Google already allows it.
import { DRIVE_SCOPE, GOOGLE_CLIENT_ID } from "../config";

interface TokenResponse {
  access_token?: string;
  expires_in?: number;
  error?: string;
}

interface TokenClient {
  requestAccessToken: (options: { prompt: string }) => void;
}

interface GoogleGlobal {
  accounts: {
    oauth2: {
      initTokenClient: (config: {
        client_id: string;
        scope: string;
        callback: (response: TokenResponse) => void;
        error_callback?: (error: { type?: string }) => void;
      }) => TokenClient;
    };
  };
}

declare global {
  interface Window {
    google?: GoogleGlobal;
  }
}

const GIS_SCRIPT = "https://accounts.google.com/gsi/client";
const REFRESH_MARGIN_MS = 60_000;
let scriptLoaded: Promise<void> | null = null;
let cached: { token: string; expiresAt: number } | null = null;

function loadGis(): Promise<void> {
  if (!scriptLoaded) {
    scriptLoaded = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GIS_SCRIPT;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        scriptLoaded = null;
        reject(new Error("Google sign-in script could not be loaded"));
      };
      document.head.appendChild(script);
    });
  }
  return scriptLoaded;
}

/** Load Google's script early, so the sign-in window can open on the user's tap. */
export function preloadGoogle(): void {
  loadGis().catch(() => undefined);
}

/**
 * Return an access token. `interactive` allows Google's sign-in window (it must follow a tap);
 * a silent request only succeeds when the user already allowed this app.
 */
export async function accessToken(interactive: boolean): Promise<string> {
  if (cached && Date.now() < cached.expiresAt - REFRESH_MARGIN_MS) return cached.token;
  await loadGis();
  const google = window.google;
  if (!google) throw new Error("Google sign-in is not available");

  return new Promise<string>((resolve, reject) => {
    const client = google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: DRIVE_SCOPE,
      callback: (response) => {
        if (response.error || !response.access_token) {
          reject(new Error(response.error ?? "Google did not return a token"));
          return;
        }
        cached = { token: response.access_token, expiresAt: Date.now() + (response.expires_in ?? 3600) * 1000 };
        resolve(response.access_token);
      },
      error_callback: (error) => reject(new Error(error.type ?? "sign-in was not completed")),
    });
    client.requestAccessToken({ prompt: interactive ? "" : "none" });
  });
}

/** Forget the token in memory (sign out on this page). */
export function forgetToken(): void {
  cached = null;
}
