"use client";

import { Flag, Quote, Search, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DECISION_STYLE, ReviewBadge, ScoreBar, StatusBadge, VerdictBadge } from "@/components/verdict-badge";
import { type CandidateSummary, listCandidates, VERDICTS, type VerdictLabel } from "@/lib/api";

type Scope = "pending" | "all" | "decided";
type Sort = "score" | "alerts" | "pseudonym";

const GENDER: Record<string, string> = { Female: "Female", Male: "Male" };

function SessionBanner({ rows }: { rows: CandidateSummary[] }) {
  const pending = rows.filter((r) => r.status === "pending");
  const decided = rows.length - pending.length;
  const next = [...pending].sort((a, b) => a.pseudonym.localeCompare(b.pseudonym))[0];
  const share = rows.length ? decided / rows.length : 0;
  return (
    <section aria-label="Review progress" data-tour="progress" className="rounded-[1.75rem] bg-white p-6 lg:p-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-xl">
          <h1 className="text-3xl font-semibold lg:text-4xl">
            {pending.length === 0
              ? "Every application has a decision"
              : pending.length === 1
                ? "1 application left to review"
                : `${pending.length} applications left to review`}
          </h1>
          <p className="mt-2 text-muted-foreground">
            For each application, the system proposes a decision and quotes the application to support it. You
            validate it or change it.
          </p>
        </div>
        {next ? (
          <Link
            href={`/applications/${next.pseudonym}`}
            data-tour="start-reviewing"
            className="inline-flex h-11 items-center rounded-xl bg-ink px-5 text-sm font-medium text-white hover:bg-black"
          >
            {decided === 0 ? "Start reviewing" : "Continue reviewing"}
          </Link>
        ) : (
          <Link href="/decisions" className="inline-flex h-11 items-center rounded-xl bg-ink px-5 text-sm font-medium text-white">
            Open the decision log
          </Link>
        )}
      </div>
      <div className="mt-6">
        <div className="h-2 overflow-hidden rounded-full bg-[#ece5d8]">
          <div className="h-full rounded-full bg-ink transition-[width]" style={{ width: `${share * 100}%` }} />
        </div>
        <p className="mt-2 text-sm text-muted-foreground tabular-nums">
          {decided} of {rows.length} decided
        </p>
      </div>
    </section>
  );
}

function DecisionCards({
  rows,
  verdict,
  review,
  onVerdict,
  onReview,
}: {
  rows: CandidateSummary[];
  verdict: VerdictLabel | "";
  review: boolean;
  onVerdict: (v: VerdictLabel | "") => void;
  onReview: (v: boolean) => void;
}) {
  const card = "rounded-2xl p-4 text-left transition-shadow hover:shadow-[0_0_0_2px_var(--ink)] aria-pressed:shadow-[0_0_0_2px_var(--ink)]";
  const reviewCount = rows.filter((r) => r.request_further_review).length;
  return (
    <section aria-label="Proposed decisions" data-tour="decision-cards" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {VERDICTS.map((v) => {
        const style = DECISION_STYLE[v];
        const count = rows.filter((r) => r.proposed === v).length;
        return (
          <button
            key={v}
            type="button"
            aria-pressed={verdict === v}
            onClick={() => onVerdict(verdict === v ? "" : v)}
            className={`${card} ${style.bg} ${style.ink}`}
          >
            <span className="block font-display text-4xl font-semibold tabular-nums">{count}</span>
            <span className="mt-1 block text-sm font-medium">{v}</span>
            <span className="block text-xs opacity-75">proposed by the system</span>
          </button>
        );
      })}
      <button
        type="button"
        aria-pressed={review}
        onClick={() => onReview(!review)}
        className={`${card} bg-review text-review-ink`}
      >
        <span className="block font-display text-4xl font-semibold tabular-nums">{reviewCount}</span>
        <span className="mt-1 block text-sm font-medium">Further review</span>
        <span className="block text-xs opacity-75">requested by the system</span>
      </button>
    </section>
  );
}

function CandidateRow({ r }: { r: CandidateSummary }) {
  const meta = [r.gender ? GENDER[r.gender] ?? r.gender : null, r.age ? `${r.age} years old` : null, r.citizenship]
    .filter(Boolean)
    .join(", ");
  return (
    <li>
      <Link
        href={`/applications/${r.pseudonym}`}
        className="grid grid-cols-1 gap-3 rounded-2xl bg-white px-4 py-3 hover:shadow-[0_0_0_1px_var(--ink)] md:grid-cols-[10rem_1fr_11rem_10rem_8rem] md:items-center"
      >
        <span>
          <span className="block font-medium tabular-nums">{r.pseudonym}</span>
          <span className="block text-xs text-muted-foreground">{meta || "No profile data"}</span>
        </span>
        <span className="flex flex-wrap gap-1">
          <VerdictBadge verdict={r.proposed} />
          <ReviewBadge review={r.request_further_review} />
        </span>
        <ScoreBar value={r.total} max={r.max_total} verdict={r.proposed} label={`Total for ${r.pseudonym}`} />
        <span className="flex items-center gap-3 text-sm text-muted-foreground">
          <span title="Alerts" className={`inline-flex items-center gap-1 ${r.alerts ? "font-medium text-destructive" : ""}`}>
            <TriangleAlert className="size-3.5" aria-hidden />
            <span className="sr-only">Alerts:</span>
            {r.alerts}
          </span>
          <span title="Concerns" className="inline-flex items-center gap-1">
            <Flag className="size-3.5" aria-hidden />
            <span className="sr-only">Concerns:</span>
            {r.concerns}
          </span>
          <span title="Verified quotes" className="inline-flex items-center gap-1 tabular-nums">
            <Quote className="size-3.5" aria-hidden />
            <span className="sr-only">Verified quotes:</span>
            {r.quotes_verified}/{r.quotes_total}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-1 md:justify-end">
          {r.retained ? <VerdictBadge verdict={r.retained} /> : <StatusBadge status={r.status} />}
        </span>
      </Link>
    </li>
  );
}

export default function CandidatesPage() {
  const [rows, setRows] = useState<CandidateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("pending");
  const [verdict, setVerdict] = useState<VerdictLabel | "">("");
  const [review, setReview] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<Sort>("score");

  useEffect(() => {
    listCandidates()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  const shown = useMemo(() => {
    if (!rows) return [];
    const filtered = rows.filter(
      (r) =>
        (scope === "all" || (scope === "pending" ? r.status === "pending" : r.status !== "pending")) &&
        (!verdict || r.proposed === verdict) &&
        (!review || r.request_further_review) &&
        (!search || r.pseudonym.toLowerCase().includes(search.trim().toLowerCase())),
    );
    return [...filtered].sort((a, b) => {
      if (sort === "pseudonym") return a.pseudonym.localeCompare(b.pseudonym);
      if (sort === "alerts") return b.alerts - a.alerts || a.pseudonym.localeCompare(b.pseudonym);
      return (b.total ?? -1) - (a.total ?? -1) || a.pseudonym.localeCompare(b.pseudonym);
    });
  }, [rows, scope, verdict, review, search, sort]);

  if (error) {
    return (
      <p role="alert" className="rounded-2xl bg-reject p-4 text-sm text-reject-ink">
        The API is not responding ({error}). Start “eit-api”, then reload the page.
      </p>
    );
  }
  if (!rows) return <p className="text-sm text-muted-foreground">Loading applications…</p>;
  if (rows.length === 0) {
    return (
      <p className="rounded-2xl bg-white p-6">
        No applications loaded yet. Run “eit-api-load” to import the proposed decisions.
      </p>
    );
  }

  const counts: Record<Scope, number> = {
    pending: rows.filter((r) => r.status === "pending").length,
    all: rows.length,
    decided: rows.filter((r) => r.status !== "pending").length,
  };
  const scopes: [Scope, string][] = [
    ["pending", "To review"],
    ["decided", "Decided"],
    ["all", "All"],
  ];
  const filtersActive = verdict || review || search;

  return (
    <div className="space-y-6">
      <SessionBanner rows={rows} />
      <DecisionCards rows={rows} verdict={verdict} review={review} onVerdict={setVerdict} onReview={setReview} />

      <section aria-label="Applications" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3" data-tour="list-tools">
          <div role="tablist" aria-label="Status" className="inline-flex rounded-xl bg-[#efe8dc] p-1">
            {scopes.map(([key, label]) => (
              <button
                key={key}
                role="tab"
                type="button"
                aria-selected={scope === key}
                onClick={() => setScope(key)}
                className="rounded-lg px-3 py-1.5 text-sm aria-selected:bg-white aria-selected:font-medium"
              >
                {label} <span className="tabular-nums text-muted-foreground">{counts[key]}</span>
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative">
              <span className="sr-only">Search by pseudonym</span>
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Pseudonym"
                className="h-9 w-40 rounded-xl border border-input bg-white pr-2 pl-8 text-sm"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Sort by
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as Sort)}
                className="h-9 rounded-xl border border-input bg-white px-2 text-sm text-ink"
              >
                <option value="score">Highest total</option>
                <option value="alerts">Alerts first</option>
                <option value="pseudonym">Pseudonym</option>
              </select>
            </label>
          </div>
        </div>

        {filtersActive && (
          <p className="flex flex-wrap items-center gap-2 text-sm">
            {shown.length} application{shown.length === 1 ? "" : "s"} match{shown.length === 1 ? "es" : ""} the filters.
            <button
              type="button"
              className="underline underline-offset-4"
              onClick={() => {
                setVerdict("");
                setReview(false);
                setSearch("");
              }}
            >
              Clear filters
            </button>
          </p>
        )}

        {shown.length > 0 ? (
          <ul className="space-y-2">
            {shown.map((r) => (
              <CandidateRow key={r.pseudonym} r={r} />
            ))}
          </ul>
        ) : (
          <p className="rounded-2xl bg-white p-6 text-sm text-muted-foreground">
            {scope === "decided" && counts.decided === 0
              ? "No decisions recorded yet. Open an application to validate or change its proposal."
              : "No application matches. Clear a filter or switch tabs."}
          </p>
        )}
      </section>

      <p className="text-xs text-muted-foreground">
        Gender, age and citizenship are used for filters and eligibility checks only. They are never sent to the
        language model.
      </p>
    </div>
  );
}
