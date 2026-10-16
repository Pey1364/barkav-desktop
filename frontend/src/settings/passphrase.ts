// The passphrase is kept in this phone's browser storage, once (ADR-0005). It is never sent to
// Google or written to the repository. If storage is blocked, the app asks again next time.
const KEY = "barkav-field.passphrase";

export function loadPassphrase(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function savePassphrase(value: string): void {
  try {
    window.localStorage.setItem(KEY, value);
  } catch {
    throw new Error("the passphrase could not be saved on this device");
  }
}

export function clearPassphrase(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // Nothing to clear when storage is blocked.
  }
}
