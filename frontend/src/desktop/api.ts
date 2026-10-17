// The desktop page talks only to the local server on this computer (backend/barkav_field/server.py).
// Nothing here leaves the machine.
export const LOCAL_API = "http://127.0.0.1:8765/api/v1";

export interface DocumentRow {
  id: string;
  mode: "quick" | "detailed";
  caption: string;
  received_at: string;
  imported_at: string;
  image_count: number;
}

export interface ReviewRow {
  id: string;
  status: "new" | "under_review" | "approved" | "rejected";
  title: string;
  transaction_type: string;
  category: string;
  document_kind: "financial" | "non_financial" | null;
  note: string;
  event_date: string;
  amount: string;
  phase: string;
  decided_by: string | null;
  decided_at: string | null;
  updated_at: string;
}

export interface ReportRow {
  id: string;
  report_date: string;
  body: string;
  imported_at: string;
  details: { phase?: string; weather?: string; temperature?: string; calendar?: string };
}

export interface ClassifyInput {
  title: string;
  transaction_type: string;
  document_kind: "financial" | "non_financial";
  event_date: string;
  amount: string;
  phase: string;
}

export interface EditInput extends ClassifyInput {
  caption: string;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${LOCAL_API}${path}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function send(method: "POST" | "DELETE", path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(`${LOCAL_API}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(detail.detail ?? `HTTP ${response.status}`);
  }
  return response.json();
}

export const api = {
  documents: () => getJson<DocumentRow[]>("/documents"),
  reviews: () => getJson<ReviewRow[]>("/review-items"),
  reports: () => getJson<ReportRow[]>("/daily-reports"),
  edit: (id: string, input: EditInput) => send("POST", `/documents/${id}/edit`, input),
  remove: (id: string) => send("DELETE", `/documents/${id}`),
  decide: (id: string, decision: "approve" | "reject") => send("POST", `/review-items/${id}/decision`, { decision }),
  photoUrl: (documentId: string, position: number) => `${LOCAL_API}/documents/${documentId}/images/${position}`,
};
