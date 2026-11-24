// Accès à l'API FastAPI (eit-api). Adresse réglable par NEXT_PUBLIC_API_URL.
// Sur Vercel, l'interface et l'API partagent la même adresse (vercel.json) : chemins relatifs.

import { readAccessCode } from "@/lib/access";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NEXT_PUBLIC_VERCEL_ENV ? "" : "http://127.0.0.1:8000");

/** Refus du code d'accès (HTTP 401) : l'interface redemande le code. */
export class AccessCodeError extends Error {}

// Guide d'évaluation 2027 : trois décisions, et un booléen distinct de revue complémentaire.
export const VERDICTS = ["Interview Invitation", "Waitlist", "Interview Reject"] as const;
export type VerdictLabel = (typeof VERDICTS)[number];

export type Status = "pending" | "validated" | "modified";

export interface CandidateSummary {
  pseudonym: string;
  proposed: VerdictLabel | null;
  request_further_review: boolean;
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
  retained_review: boolean | null;
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
  proposed: VerdictLabel | null;
  request_further_review: boolean;
  rule: string;
  review_reasons: string[];
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
  proposed: VerdictLabel | null;
  retained: VerdictLabel;
  proposed_review: boolean;
  retained_review: boolean;
  comment: string;
  created_at: string;
}

export interface CandidateDetail extends CandidateSummary {
  verdict: Verdict;
  dossier: { pseudonym: string; texts: DossierText[] };
  decisions: Decision[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const code = readAccessCode();
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(code ? { "X-Access-Code": code } : {}), ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event(ACCESS_DENIED_EVENT));
    throw new AccessCodeError("Access code required.");
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
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

export const ACCESS_DENIED_EVENT = "code-acces-refuse";

/** 200 si le code est bon ou si l'API n'en exige pas ; AccessCodeError sinon. */
export const checkAccess = () => request<{ status: string; code_required: boolean }>("/api/access");

export const listCandidates = () => request<CandidateSummary[]>("/api/candidates");
export const getCandidate = (pseudonym: string) =>
  request<CandidateDetail>(`/api/candidates/${encodeURIComponent(pseudonym)}`);
export const postDecision = (
  pseudonym: string,
  body: {
    evaluator: string;
    action: "validate" | "modify";
    retained?: VerdictLabel;
    request_further_review?: boolean;
    comment?: string;
  },
) =>
  request<Decision>(`/api/candidates/${encodeURIComponent(pseudonym)}/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const listDecisions = () => request<Decision[]>("/api/decisions");

export const SECTION_LABELS: Record<string, string> = {
  essay: "Written answer",
  personal_statement: "Personal statement video",
  assessment_reflection: "Assessment reflection video",
  attachment: "Attachment",
  education: "Education",
  experience: "Work experience",
  uploads: "Uploaded files",
};

// Codes techniques qui pourraient rester dans un ancien verdict, en langage d'évaluateur.
export const CODE_LABELS: Record<string, string> = {
  age_out_of_range: "age outside the eligible range",
  age_borderline: "age at the limit",
  citizenship_outside_region: "citizenship outside the eligible region",
  graduation_after_cutoff: "graduation in 2028 or later",
  graduation_review: "graduation in 2027",
  assessment_not_found: "assessment not found",
  assessment_late: "assessment submitted after the deadline",
  assessment_too_fast: "assessment completed unusually fast",
  generic_ai_responses: "generic responses",
};

/** Remplace d'éventuels codes techniques par leur libellé (les nouveaux verdicts n'en contiennent plus). */
export function humanize(text: string): string {
  return text.replace(/[a-z]+(?:_[a-z0-9]+)+/g, (code) => CODE_LABELS[code] ?? code);
}

// Marques d'anonymisation des données (en français) et leur affichage aux évaluateurs.
const PLACEHOLDERS: Record<string, string> = {
  CANDIDAT: "APPLICANT",
  PAYS: "COUNTRY",
  VILLE: "CITY",
  "NATIONALITÉ": "NATIONALITY",
  LANGUE: "LANGUAGE",
  LIEU: "PLACE",
  "TÉLÉPHONE": "PHONE",
  LIEN: "LINK",
  EMAIL: "EMAIL",
};

/** Texte affiché : marques d'anonymisation en anglais (« [PAYS] » devient « [COUNTRY] »). */
export function displayText(text: string): string {
  return text.replace(/\[(PERSONNE)_(\d+)\]|\[([A-ZÉ]+)\]/g, (match, person, n, word) =>
    person ? `[PERSON_${n}]` : `[${PLACEHOLDERS[word] ?? word}]`,
  );
}

// Retours de la session de test (visite guidée).
export type StepOutcome = "worked" | "failed" | "skipped";

export interface StepResult {
  step: string;
  title: string;
  result: StepOutcome;
  note: string;
}

export interface Feedback {
  id: number;
  evaluator: string;
  steps: StepResult[];
  ease: number | null;
  comment: string;
  created_at: string;
}

export const postFeedback = (body: { evaluator: string; steps: StepResult[]; ease: number | null; comment: string }) =>
  request<Feedback>("/api/feedback", { method: "POST", body: JSON.stringify(body) });

export const listFeedback = () => request<Feedback[]>("/api/feedback");
