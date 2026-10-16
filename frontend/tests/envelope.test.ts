import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { EnvelopeError, open, seal } from "../src/crypto/envelope";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, "fixtures");
const PASS = "test-passphrase-1";

interface Fixture {
  passphrase: string;
  envelope: Record<string, unknown>;
  payload: Record<string, unknown>;
}

describe("envelope v1 in the browser", () => {
  it("opens an envelope that Python sealed (same format, same key derivation)", async () => {
    const fixture = JSON.parse(readFileSync(join(fixtures, "python-envelope.json"), "utf-8")) as Fixture;
    const bytes = new TextEncoder().encode(JSON.stringify(fixture.envelope));
    expect(await open(bytes, fixture.passphrase)).toEqual(fixture.payload);
  });

  it("round-trips a payload with Persian text and images", async () => {
    const payload = { kind: "document", caption: "بابت آجر نما", images_b64: ["AAEC", "/9j/"] };
    const sealed = await seal(payload, PASS);
    expect(await open(sealed, PASS)).toEqual(payload);
  });

  it("writes the envelope header fields the contract names", async () => {
    const envelope = JSON.parse(new TextDecoder().decode(await seal({ kind: "x" }, PASS)));
    expect(envelope).toMatchObject({ v: 1, kdf: "scrypt", n: 32768, r: 8, p: 1 });
    expect(Object.keys(envelope).sort()).toEqual(["ct", "kdf", "n", "nonce", "p", "r", "salt", "v"]);
  });

  it("refuses a wrong passphrase", async () => {
    const sealed = await seal({ kind: "x" }, PASS);
    await expect(open(sealed, "another-passphrase")).rejects.toBeInstanceOf(EnvelopeError);
  });

  it("refuses an envelope whose ciphertext was changed", async () => {
    const envelope = JSON.parse(new TextDecoder().decode(await seal({ kind: "x" }, PASS)));
    const ct = atob(envelope.ct);
    envelope.ct = btoa(String.fromCharCode(ct.charCodeAt(0) ^ 1) + ct.slice(1));
    const bytes = new TextEncoder().encode(JSON.stringify(envelope));
    await expect(open(bytes, PASS)).rejects.toBeInstanceOf(EnvelopeError);
  });

  it("refuses bytes that are not an envelope", async () => {
    await expect(open(new TextEncoder().encode("hello"), PASS)).rejects.toBeInstanceOf(EnvelopeError);
  });

  // Run once with WRITE_FIXTURES=1 to produce the file that backend/tests reads back in Python.
  it.runIf(process.env.WRITE_FIXTURES === "1")("writes an envelope sealed here for the Python test", async () => {
    const payload = { kind: "daily_report", id: "fixture-js-1", report_date: "1405-07-24", body: "شرح آزمایشی", calendar: "jalali" };
    const sealed = await seal(payload, PASS);
    const out = { passphrase: PASS, envelope: JSON.parse(new TextDecoder().decode(sealed)), payload };
    writeFileSync(join(fixtures, "js-envelope.json"), JSON.stringify(out, null, 2), "utf-8");
  });
});
