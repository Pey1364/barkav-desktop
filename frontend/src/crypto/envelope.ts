// FIELD_ENVELOPE_V1 in the browser. It must stay byte-compatible with backend/barkav_field/envelope.py:
// scrypt (N=32768, r=8, p=1) gives a 32-byte key; AES-256-GCM seals the JSON payload with the
// associated data "barkav-field-envelope-v1". The tests check both directions against Python.
import { scryptAsync } from "@noble/hashes/scrypt";

export const ENVELOPE_VERSION = 1;
const SCRYPT = { N: 32768, r: 8, p: 1, dkLen: 32 } as const;
const AAD = new TextEncoder().encode("barkav-field-envelope-v1");

export class EnvelopeError extends Error {}

export type Payload = Record<string, unknown>;

interface EnvelopeJson {
  v: number;
  kdf: string;
  n: number;
  r: number;
  p: number;
  salt: string;
  nonce: string;
  ct: string;
}

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  // Chunked so large photos do not overflow the call stack.
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

export function fromBase64(text: string): Uint8Array {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

async function deriveKey(passphrase: string, salt: Uint8Array, n: number, r: number, p: number): Promise<CryptoKey> {
  if (!passphrase) throw new EnvelopeError("passphrase is empty");
  const keyBytes = await scryptAsync(new TextEncoder().encode(passphrase), salt, { N: n, r, p, dkLen: 32 });
  return crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

/** Seal a JSON-serialisable payload. Returns the envelope as UTF-8 JSON bytes. */
export async function seal(payload: Payload, passphrase: string): Promise<Uint8Array> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(passphrase, salt, SCRYPT.N, SCRYPT.r, SCRYPT.p);
  const plain = new TextEncoder().encode(JSON.stringify(payload));
  const sealed = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, additionalData: AAD, tagLength: 128 }, key, plain);
  const envelope: EnvelopeJson = {
    v: ENVELOPE_VERSION,
    kdf: "scrypt",
    n: SCRYPT.N,
    r: SCRYPT.r,
    p: SCRYPT.p,
    salt: toBase64(salt),
    nonce: toBase64(nonce),
    ct: toBase64(new Uint8Array(sealed)),
  };
  return new TextEncoder().encode(JSON.stringify(envelope));
}

/** Open an envelope. Throws EnvelopeError for a wrong passphrase, changed data or a bad format. */
export async function open(data: Uint8Array, passphrase: string): Promise<Payload> {
  let envelope: Partial<EnvelopeJson>;
  try {
    envelope = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(data));
  } catch {
    throw new EnvelopeError("not a JSON envelope");
  }
  if (envelope.v !== ENVELOPE_VERSION) throw new EnvelopeError("unsupported envelope version");
  if (envelope.kdf !== "scrypt") throw new EnvelopeError("unsupported key derivation");
  const n = Number(envelope.n);
  const r = Number(envelope.r);
  const p = Number(envelope.p);
  if (!Number.isInteger(n) || n < 2 || (n & (n - 1)) !== 0 || n > 2 ** 20 || r < 1 || r > 32 || p < 1 || p > 4) {
    throw new EnvelopeError("scrypt parameters out of range");
  }
  const salt = fromBase64(String(envelope.salt ?? ""));
  const nonce = fromBase64(String(envelope.nonce ?? ""));
  const ct = fromBase64(String(envelope.ct ?? ""));
  if (salt.length !== 16 || nonce.length !== 12 || ct.length < 16) throw new EnvelopeError("bad envelope fields");

  const key = await deriveKey(passphrase, salt, n, r, p);
  let plain: ArrayBuffer;
  try {
    plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce, additionalData: AAD, tagLength: 128 }, key, ct);
  } catch {
    throw new EnvelopeError("wrong passphrase or changed data");
  }
  const payload = JSON.parse(new TextDecoder().decode(plain)) as unknown;
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new EnvelopeError("payload is not an object");
  }
  return payload as Payload;
}
