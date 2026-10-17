// The phone's send and read path against an in-memory Drive. Google sign-in and the image
// re-encoding (canvas) are replaced; everything else (sealing, multipart upload, listing,
// download, opening) runs as it does in the app.
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/drive/gis", () => ({ accessToken: async () => "test-access-token" }));
vi.mock("../src/media/compress", () => ({ compressToJpeg: async () => new Uint8Array([0xff, 0xd8, 1, 2]) }));

import { open, seal } from "../src/crypto/envelope";
import { loadInbox, sendClassification, sendDecision, sendDelete, sendDocument, sendEdit, sendReport } from "../src/sync/service";

const PASS = "test-passphrase-1";
const REVIEW = { title: "خرید زمین", method: "چک", eventDate: "۱۴۰۵/۰۷/۲۴", amount: "۲۵۰۰۰۰۰۰۰", documentKind: "financial" as const };

interface StoredFile {
  folder: string;
  name: string;
  bytes: Uint8Array;
}

class FakeDrive {
  folders = new Map<string, string>();
  files = new Map<string, StoredFile>();
  private counter = 0;

  private nextId(prefix: string): string {
    this.counter += 1;
    return `${prefix}-${this.counter}`;
  }

  handle = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

    if (url.pathname === "/drive/v3/files" && method === "GET") {
      const q = url.searchParams.get("q") ?? "";
      if (q.includes("mimeType")) {
        const name = /name = '([^']+)'/.exec(q)?.[1] ?? "";
        const id = this.folders.get(name);
        return json({ files: id ? [{ id }] : [] });
      }
      const folder = /'([^']+)' in parents/.exec(q)?.[1] ?? "";
      const ids = [...this.files].filter(([, file]) => file.folder === folder).map(([id]) => ({ id }));
      return json({ files: ids });
    }
    if (url.pathname === "/drive/v3/files" && method === "POST") {
      const body = JSON.parse(String(init?.body)) as { name: string };
      const id = this.nextId("folder");
      this.folders.set(body.name, id);
      return json({ id });
    }
    if (url.pathname === "/upload/drive/v3/files" && method === "POST") {
      const parsed = parseMultipart(new Uint8Array(init?.body as Uint8Array), new Headers(init?.headers).get("Content-Type") ?? "");
      const id = this.nextId("file");
      this.files.set(id, { folder: parsed.metadata.parents[0], name: parsed.metadata.name, bytes: parsed.content });
      return json({ id });
    }
    if (url.pathname.startsWith("/drive/v3/files/") && method === "GET") {
      const id = url.pathname.split("/").pop() ?? "";
      const file = this.files.get(id);
      return file ? new Response(file.bytes) : new Response("missing", { status: 404 });
    }
    return new Response("unexpected request", { status: 500 });
  };
}

/** Split a multipart/related body into its JSON metadata and its binary content, byte for byte. */
function parseMultipart(body: Uint8Array, contentType: string) {
  const boundary = contentType.split("boundary=")[1];
  let text = "";
  for (const byte of body) text += String.fromCharCode(byte);
  const metaStart = text.indexOf("\r\n\r\n") + 4;
  const metaEnd = text.indexOf(`\r\n--${boundary}\r\n`, metaStart);
  const metadata = JSON.parse(new TextDecoder().decode(body.slice(metaStart, metaEnd)));
  const contentStart = text.indexOf("\r\n\r\n", metaEnd + 4) + 4;
  const contentEnd = text.lastIndexOf(`\r\n--${boundary}--`);
  return { metadata, content: body.slice(contentStart, contentEnd) };
}

let drive: FakeDrive;

beforeEach(() => {
  drive = new FakeDrive();
  vi.stubGlobal("fetch", drive.handle);
});

describe("phone sync against Drive", () => {
  it("sends a detailed document and reads it back as under review", async () => {
    await sendDocument(PASS, {
      id: "doc-detailed",
      mode: "detailed",
      caption: "فاکتور زمین",
      photos: [new File([], "a.jpg")],
      review: REVIEW,
    });

    const state = await loadInbox(PASS);

    expect(state.failed).toBe(0);
    expect(state.items).toHaveLength(1);
    expect(state.items[0]).toMatchObject({ id: "doc-detailed", caption: "فاکتور زمین", status: "review", photos: 1 });
  });

  it("keeps a quick document pending until the phone classifies it", async () => {
    await sendDocument(PASS, { id: "doc-quick", mode: "quick", caption: "میلگرد", photos: [new File([], "b.jpg")] });
    expect((await loadInbox(PASS)).items[0].status).toBe("pending");

    await sendClassification(PASS, "doc-quick", REVIEW);

    expect((await loadInbox(PASS)).items[0].status).toBe("review");
  });

  it("applies the phone's decision and shows it", async () => {
    await sendDocument(PASS, { id: "doc-decide", mode: "detailed", caption: "x", photos: [new File([], "c.jpg")], review: REVIEW });
    await sendDecision(PASS, "doc-decide", "reject");

    const [item] = (await loadInbox(PASS)).items;

    expect(item).toMatchObject({ status: "decided", decision: "reject" });
  });

  it("shows the desktop's published outcome and lets it override the phone's decision", async () => {
    await sendDocument(PASS, { id: "doc-desk", mode: "detailed", caption: "y", photos: [new File([], "e.jpg")], review: REVIEW });
    await sendDecision(PASS, "doc-desk", "approve");
    const folder = drive.folders.get("BARKAV Field Inbox") ?? "";
    drive.files.set("desk-status", { folder, name: "status.json", bytes: await seal({ kind: "review_status", item_id: "doc-desk", status: "rejected", decided_at: "t" }, PASS) });

    const [item] = (await loadInbox(PASS)).items;

    expect(item).toMatchObject({ status: "decided", decision: "reject", decidedBy: "desktop" });
  });

  it("sends the daily report with an ASCII Jalali date and reads its details", async () => {
    await sendReport(PASS, {
      id: "report-1",
      reportDate: "۱۴۰۵/۰۷/۲۴",
      phase: "۱۴ - وال مش",
      weather: "آفتابی",
      temperature: "۲۸",
      body: "نصب تیغه‌ها",
    });

    const [stored] = [...drive.files.values()];
    const sent = await open(stored.bytes, PASS);
    expect(sent).toMatchObject({ kind: "daily_report", report_date: "1405-07-24", calendar: "jalali" });

    const state = await loadInbox(PASS);
    expect(state.reports).toEqual([
      { id: "report-1", reportDate: "۱۴۰۵/۰۷/۲۴", phase: "۱۴ - وال مش", weather: "آفتابی", temperature: "۲۸", body: "نصب تیغه‌ها" },
    ]);
  });

  it("counts files it cannot open instead of showing them", async () => {
    await sendDocument(PASS, { id: "doc-secret", mode: "quick", caption: "x", photos: [new File([], "d.jpg")] });

    const state = await loadInbox("another-passphrase");

    expect(state.items).toHaveLength(0);
    expect(state.failed).toBe(1);
  });
});

describe("phone edit and delete against Drive", () => {
  const detailed = { title: "هزینه ساخت", method: "چک", phase: "۰۳ - طراحی", eventDate: "۱۴۰۵/۰۷/۲۴", amount: "۱۵۰۰۰۰۰", documentKind: "financial" as const };

  it("shows the phase and applies a later edit of caption and classification", async () => {
    await sendDocument(PASS, { id: "doc-edit", mode: "detailed", caption: "اولیه", photos: [new File([], "f.jpg")], review: detailed });
    await sendEdit(PASS, "doc-edit", "شرح تازه", { ...detailed, phase: "۰۴ - کف‌سازی", amount: "۲۰۰۰۰۰۰" });

    const [item] = (await loadInbox(PASS)).items;

    expect(item.caption).toBe("شرح تازه");
    expect(item.review).toMatchObject({ title: "هزینه ساخت", phase: "۰۴ - کف‌سازی", amount: "2000000" });
  });

  it("hides a deleted document from the list", async () => {
    await sendDocument(PASS, { id: "doc-gone", mode: "quick", caption: "حذفی", photos: [new File([], "g.jpg")] });
    await sendDelete(PASS, "doc-gone");

    const state = await loadInbox(PASS);

    expect(state.items.find((item) => item.id === "doc-gone")).toBeUndefined();
  });
});
