// Accès à l'API FastAPI (eit-api). Adresse réglable par NEXT_PUBLIC_API_URL.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export const VERDICTS = [
  "Interview Invitation",
  "Waitlist",
  "Interview Reject",
  "Request Final Review",
] as const;
export type VerdictLabel = (typeof VERDICTS)[number];

export type Status = "à traiter" | "validé" | "modifié";

export interface CandidateSummary {
  pseudonym: string;
  proposed: VerdictLabel;
  total: number | null;
  max_total: number;
  alerts: number;
  concerns: number;
  quotes_verified: number;
  quotes_total: number;
  gender: string | null;
  age: number | null;
  citizenship: string | null;
  status: Status;
  retained: VerdictLabel | null;
}

export interface QuoteLocation {
  unit_index: number;
  section: string;
  label: string | null;
  page: number | null;
  start: number | null;
  end: number | null;
  char_start: number;
  char_end: number;
}

export interface CriterionResult {
  key: string;
  name: string;
  max_points: number;
  score: number;
  reason: string;
  quote: string;
  quote_verified: boolean;
  quote_location: QuoteLocation | null;
}

export interface ConcernResult {
  key: string;
  name: string;
  source: "contrôle" | "modèle";
  detail: string;
  quote: string | null;
  quote_verified: boolean | null;
}

export interface Finding {
  code: string;
  severity: "alert" | "to_check";
  message: string;
}

export interface Verdict {
  pseudonym: string;
  proposed: VerdictLabel;
  rule: string;
  total: number | null;
  max_total: number;
  criteria: CriterionResult[];
  concerns: ConcernResult[];
  findings: Finding[];
  quotes_verified: number;
  quotes_total: number;
  llm: { model: string; attempts: number; seconds: number; schema_valid: boolean };
}

export interface DossierText {
  section: string;
  label: string | null;
  page: number | null;
  start: number | null;
  end: number | null;
  text: string;
}

export interface Decision {
  id: number;
  pseudonym: string;
  evaluator: string;
  action: "validate" | "modify";
  proposed: VerdictLabel;
  retained: VerdictLabel;
  comment: string;
  created_at: string;
}

export interface CandidateDetail extends CandidateSummary {
  verdict: Verdict;
  dossier: { pseudonym: string; texts: DossierText[] };
  decisions: Decision[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // réponse sans JSON
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const listCandidates = () => request<CandidateSummary[]>("/api/candidates");
export const getCandidate = (pseudonym: string) =>
  request<CandidateDetail>(`/api/candidates/${encodeURIComponent(pseudonym)}`);
export const postDecision = (
  pseudonym: string,
  body: { evaluator: string; action: "validate" | "modify"; retained?: VerdictLabel; comment?: string },
) =>
  request<Decision>(`/api/candidates/${encodeURIComponent(pseudonym)}/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const SECTION_LABELS: Record<string, string> = {
  essay: "Réponse libre",
  personal_statement: "Vidéo de présentation",
  assessment_reflection: "Vidéo de réflexion",
  attachment: "Pièce jointe",
  education: "Formation",
  experience: "Expérience",
  uploads: "Fichiers envoyés",
};
