// Google Drive v3 over fetch, limited to what the app needs: find or create its inbox folder,
// upload one sealed file, list the folder and download files. Only files created by this app
// (drive.file) are visible to it.
import { INBOX_FOLDER_NAME } from "../config";

const DRIVE_API = "https://www.googleapis.com/drive/v3";
const UPLOAD_API = "https://www.googleapis.com/upload/drive/v3";
const FOLDER_MIME = "application/vnd.google-apps.folder";

export class DriveError extends Error {}

async function request(token: string, url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    // The message carries only the status code, never the token or the URL.
    throw new DriveError(`Drive request failed with HTTP ${response.status}`);
  }
  return response;
}

export async function findOrCreateFolder(token: string, name: string = INBOX_FOLDER_NAME): Promise<string> {
  const query = `name = '${name}' and mimeType = '${FOLDER_MIME}' and trashed = false`;
  const params = new URLSearchParams({ q: query, fields: "files(id)", pageSize: "10" });
  const found = (await (await request(token, `${DRIVE_API}/files?${params}`)).json()) as { files?: { id: string }[] };
  const existing = found.files?.[0];
  if (existing) return existing.id;

  const created = await request(token, `${DRIVE_API}/files?fields=id`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, mimeType: FOLDER_MIME }),
  });
  const body = (await created.json()) as { id?: string };
  if (!body.id) throw new DriveError("Drive did not return the folder id");
  return body.id;
}

/** Create one file in the folder with a single multipart request. */
export async function uploadFile(token: string, folderId: string, name: string, content: Uint8Array): Promise<string> {
  const boundary = `barkav-${crypto.randomUUID()}`;
  const encoder = new TextEncoder();
  const metadata = JSON.stringify({ name, parents: [folderId] });
  const head = encoder.encode(
    `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${metadata}\r\n` +
      `--${boundary}\r\nContent-Type: application/octet-stream\r\n\r\n`,
  );
  const tail = encoder.encode(`\r\n--${boundary}--\r\n`);
  const body = new Uint8Array(head.length + content.length + tail.length);
  body.set(head, 0);
  body.set(content, head.length);
  body.set(tail, head.length + content.length);

  const response = await request(token, `${UPLOAD_API}/files?uploadType=multipart&fields=id`, {
    method: "POST",
    headers: { "Content-Type": `multipart/related; boundary=${boundary}` },
    body,
  });
  const created = (await response.json()) as { id?: string };
  if (!created.id) throw new DriveError("Drive did not return the uploaded file id");
  return created.id;
}

/** Ids of the files in the folder, oldest first, across all pages. */
export async function listFiles(token: string, folderId: string): Promise<string[]> {
  const ids: string[] = [];
  let pageToken: string | undefined;
  do {
    const params = new URLSearchParams({
      q: `'${folderId}' in parents and trashed = false`,
      fields: "nextPageToken,files(id)",
      orderBy: "createdTime",
      pageSize: "200",
    });
    if (pageToken) params.set("pageToken", pageToken);
    const data = (await (await request(token, `${DRIVE_API}/files?${params}`)).json()) as {
      files?: { id: string }[];
      nextPageToken?: string;
    };
    for (const file of data.files ?? []) ids.push(file.id);
    pageToken = data.nextPageToken;
  } while (pageToken);
  return ids;
}

export async function downloadFile(token: string, fileId: string): Promise<Uint8Array> {
  const response = await request(token, `${DRIVE_API}/files/${fileId}?alt=media`);
  return new Uint8Array(await response.arrayBuffer());
}
