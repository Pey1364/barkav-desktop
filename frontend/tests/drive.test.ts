import { afterEach, describe, expect, it, vi } from "vitest";
import { DriveError, findOrCreateFolder, listFiles, uploadFile } from "../src/drive/drive";

const TOKEN = "test-access-token-value";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Drive from the browser", () => {
  it("sends the token in the header, never in the URL", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ files: [{ id: "folder-1" }] }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await findOrCreateFolder(TOKEN)).toBe("folder-1");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).not.toContain(TOKEN);
    expect(new Headers(init.headers).get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("creates the inbox folder when it does not exist yet", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url.split("?")[0]}`);
      return init?.method === "POST" ? jsonResponse({ id: "new-folder" }) : jsonResponse({ files: [] });
    }));

    expect(await findOrCreateFolder(TOKEN)).toBe("new-folder");
    expect(calls).toEqual([
      "GET https://www.googleapis.com/drive/v3/files",
      "POST https://www.googleapis.com/drive/v3/files",
    ]);
  });

  it("uploads one multipart file with its metadata and the exact bytes", async () => {
    let sentBody = new Uint8Array();
    let sentType = "";
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      expect(url).toContain("uploadType=multipart");
      sentType = new Headers(init?.headers).get("Content-Type") ?? "";
      sentBody = new Uint8Array(init?.body as Uint8Array);
      return jsonResponse({ id: "uploaded-1" });
    }));
    const content = new Uint8Array([0, 1, 2, 250, 255]);

    expect(await uploadFile(TOKEN, "folder-1", "doc-1.json", content)).toBe("uploaded-1");

    const boundary = sentType.split("boundary=")[1];
    const text = new TextDecoder("latin1").decode(sentBody);
    expect(sentType.startsWith("multipart/related; boundary=barkav-")).toBe(true);
    expect(text).toContain(`--${boundary}\r\nContent-Type: application/json; charset=UTF-8`);
    expect(text).toContain('{"name":"doc-1.json","parents":["folder-1"]}');
    expect(sentBody.slice(-content.length - boundary.length - 8, -boundary.length - 8)).toEqual(content);
    expect(text.endsWith(`--${boundary}--\r\n`)).toBe(true);
  });

  it("lists every page of the folder", async () => {
    let page = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      page += 1;
      return page === 1
        ? jsonResponse({ files: [{ id: "a" }, { id: "b" }], nextPageToken: "next" })
        : jsonResponse({ files: [{ id: "c" }] });
    }));

    expect(await listFiles(TOKEN, "folder-1")).toEqual(["a", "b", "c"]);
  });

  it("reports the HTTP status without the token", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("denied", { status: 403 })));
    await expect(findOrCreateFolder(TOKEN)).rejects.toThrow(DriveError);
    await expect(findOrCreateFolder(TOKEN)).rejects.not.toThrow(TOKEN);
  });
});
