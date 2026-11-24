"use client";

import { ChevronLeft, ChevronRight, CircleAlert, Flag, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { DECISION_STYLE, ReviewBadge, ScoreBar, StatusBadge, VerdictBadge } from "@/components/verdict-badge";
import {
  type CandidateDetail,
  type CandidateSummary,
  type CriterionResult,
  type DossierText,
  displayText,
  getCandidate,
  humanize,
  listCandidates,
  postDecision,
  SECTION_LABELS,
  VERDICTS,
  type VerdictLabel,
} from "@/lib/api";
import { useEvaluator } from "@/lib/evaluator";

interface Mark {
  start: number;
  end: number;
  key: string;
}

const GENDER: Record<string, string> = { Female: "Female", Male: "Male" };

function where(text: DossierText): string {
  const parts = [SECTION_LABELS[text.section] ?? text.section];
  if (text.page) parts.push(`page ${text.page}`);
  if (text.start !== null && text.end !== null) parts.push(`${text.start.toFixed(0)}–${text.end.toFixed(0)} s`);
  return parts.join(", ");
}

function Highlighted({ text, marks, active }: { text: string; marks: Mark[]; active: string | null }) {
  const sorted = [...marks].sort((a, b) => a.start - b.start);
  const pieces: React.ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((mark, index) => {
    if (mark.start < cursor) return; // chevauchement : la première citation l'emporte
    pieces.push(displayText(text.slice(cursor, mark.start)));
    pieces.push(
      <mark
        key={index}
        id={`citation-${mark.key}`}
        className={`rounded px-0.5 text-ink transition-colors ${mark.key === active ? "bg-waitlist" : "bg-waitlist/45"}`}
      >
        {displayText(text.slice(mark.start, mark.end))}
      </mark>,
    );
    cursor = mark.end;
  });
  pieces.push(displayText(text.slice(cursor)));
  return <p className="text-[0.95rem] leading-relaxed whitespace-pre-wrap">{pieces}</p>;
}

function CriterionCard({ c, active, onShow }: { c: CriterionResult; active: boolean; onShow: () => void }) {
  const unsupported = c.score > 0 && !c.quote;
  return (
    <article className={`rounded-2xl bg-white p-4 ${active ? "shadow-[0_0_0_2px_var(--ink)]" : ""}`}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold">{c.name}</h3>
      </div>
      <div className="mt-2">
        <ScoreBar value={c.score} max={c.max_points} label={`Score: ${c.name}`} />
      </div>
      <p className="mt-3 text-sm leading-relaxed">{displayText(c.reason)}</p>
      {c.quote ? (
        <div className="mt-3 space-y-2">
          <blockquote className="border-l-2 border-ink/20 pl-3 text-sm text-muted-foreground italic">“{displayText(c.quote)}”</blockquote>
          {c.quote_verified ? (
            <button type="button" onClick={onShow} className="text-sm font-medium underline underline-offset-4">
              Show the quote in the application
            </button>
          ) : (
            <p className="flex items-start gap-2 rounded-xl bg-reject/60 p-2 text-sm text-reject-ink">
              <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              Quote not found word for word in the application: it is not evidence.
            </p>
          )}
        </div>
      ) : unsupported ? (
        <p className="mt-3 flex items-start gap-2 rounded-xl bg-waitlist/50 p-2 text-sm text-waitlist-ink">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          Score without a quote: nothing in the application supports it. Check it yourself.
        </p>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">No quote, score of zero.</p>
      )}
    </article>
  );
}

function DecisionForm({
  data,
  evaluator,
  onSaved,
}: {
  data: CandidateDetail;
  evaluator: string;
  onSaved: (message: string) => void;
}) {
  const v = data.verdict;
  const [modifying, setModifying] = useState(false);
  const [retained, setRetained] = useState<VerdictLabel | "">(v.proposed ?? "");
  const [review, setReview] = useState(v.request_further_review);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unchanged = retained === v.proposed && review === v.request_further_review;

  const submit = async (action: "validate" | "modify") => {
    setSaving(true);
    setError(null);
    try {
      await postDecision(data.pseudonym, {
        evaluator,
        action,
        ...(action === "modify" ? { retained: retained || undefined, request_further_review: review, comment } : {}),
      });
      setModifying(false);
      setComment("");
      onSaved(action === "validate" ? "Proposal validated." : "Decision changed.");
    } catch (e) {
      setError(`Decision not saved: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  if (!evaluator) {
    return (
      <p className="rounded-xl bg-review p-3 text-sm text-review-ink">
        Enter your name in the sidebar first: it signs each decision.
      </p>
    );
  }

  if (!modifying) {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          {v.proposed && (
            <button
              type="button"
              disabled={saving}
              onClick={() => submit("validate")}
              className="h-11 rounded-xl bg-ink px-5 text-sm font-medium text-white hover:bg-black disabled:opacity-40"
            >
              Validate the proposal
            </button>
          )}
          <button
            type="button"
            disabled={saving}
            onClick={() => setModifying(true)}
            className={`h-11 rounded-xl px-5 text-sm font-medium ${
              v.proposed ? "border border-ink bg-white" : "bg-ink text-white"
            }`}
          >
            {v.proposed ? "Change decision" : "Choose a decision"}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">Signing as {evaluator}.</p>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </div>
    );
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit("modify");
      }}
    >
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Decision</legend>
        <div className="flex flex-wrap gap-2">
          {VERDICTS.map((x) => {
            const style = DECISION_STYLE[x];
            return (
              <label
                key={x}
                className={`cursor-pointer rounded-xl px-3 py-2 text-sm ${style.bg} ${style.ink} ${
                  retained === x ? "shadow-[0_0_0_2px_var(--ink)]" : "opacity-70"
                }`}
              >
                <input
                  type="radio"
                  name="decision"
                  value={x}
                  checked={retained === x}
                  onChange={() => setRetained(x)}
                  className="sr-only"
                />
                {x}
              </label>
            );
          })}
        </div>
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={review} onChange={(e) => setReview(e.target.checked)} className="size-4 accent-ink" />
        Request further review
      </label>
      <label className="block space-y-1 text-sm">
        <span className="font-medium">Why are you changing it?</span>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          required
          className="w-full rounded-xl border border-input bg-white p-2"
        />
      </label>
      {unchanged && retained && (
        <p className="text-sm text-muted-foreground">This is the proposal unchanged: use “Validate the proposal” instead.</p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={!retained || !comment.trim() || saving || unchanged}
          className="h-11 rounded-xl bg-ink px-5 text-sm font-medium text-white disabled:opacity-40"
        >
          Save the change
        </button>
        <button type="button" onClick={() => setModifying(false)} className="h-11 rounded-xl px-4 text-sm">
          Cancel
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </form>
  );
}

export function CandidateView({ pseudonym }: { pseudonym: string }) {
  const evaluator = useEvaluator();
  const [data, setData] = useState<CandidateDetail | null>(null);
  const [all, setAll] = useState<CandidateSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const reload = useCallback(
    () =>
      Promise.all([getCandidate(pseudonym), listCandidates()])
        .then(([detail, list]) => {
          setData(detail);
          setAll(list);
        })
        .catch((e: Error) => setError(e.message)),
    [pseudonym],
  );
  useEffect(() => {
    reload();
  }, [reload]);

  // Même ordre que « Continue reviewing » : par pseudonyme.
  const order = useMemo(() => [...all].sort((a, b) => a.pseudonym.localeCompare(b.pseudonym)), [all]);
  const position = order.findIndex((c) => c.pseudonym === pseudonym);
  const previous = position > 0 ? order[position - 1] : null;
  const next = position >= 0 && position < order.length - 1 ? order[position + 1] : null;
  const nextPending =
    order.slice(position + 1).find((c) => c.status === "pending") ??
    order.slice(0, Math.max(position, 0)).find((c) => c.status === "pending") ??
    null;

  const marks = useMemo(() => {
    const byUnit = new Map<number, Mark[]>();
    data?.verdict.criteria.forEach((c) => {
      const loc = c.quote_location;
      if (!c.quote_verified || !loc) return;
      const list = byUnit.get(loc.unit_index) ?? [];
      list.push({ start: loc.char_start, end: loc.char_end, key: c.key });
      byUnit.set(loc.unit_index, list);
    });
    return byUnit;
  }, [data]);

  const show = (key: string) => {
    setActive(key);
    document.getElementById(`citation-${key}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  if (error) {
    return (
      <p role="alert" className="rounded-2xl bg-reject p-4 text-sm text-reject-ink">
        Could not load {pseudonym} ({error}).{" "}
        <Link href="/" className="underline">
          Back to applications
        </Link>
      </p>
    );
  }
  if (!data) return <p className="text-sm text-muted-foreground">Loading application…</p>;

  const v = data.verdict;
  const tone = v.proposed ? DECISION_STYLE[v.proposed] : null;
  const meta = [data.gender ? GENDER[data.gender] ?? data.gender : null, data.age ? `${data.age} years old` : null, data.citizenship]
    .filter(Boolean)
    .join(", ");
  const attention = v.findings.length + v.concerns.length;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-ink">
            <ChevronLeft className="size-4" aria-hidden /> Applications
          </Link>
          <h1 className="text-2xl font-semibold tabular-nums">{data.pseudonym}</h1>
          <StatusBadge status={data.status} />
        </div>
        <nav aria-label="Neighbouring applications" className="flex items-center gap-2">
          {position >= 0 && (
            <span className="text-sm text-muted-foreground tabular-nums">
              Application {position + 1} of {order.length}
            </span>
          )}
          <Link
            aria-disabled={!previous}
            href={previous ? `/applications/${previous.pseudonym}` : "#"}
            className={`grid size-9 place-items-center rounded-xl bg-white ${previous ? "" : "pointer-events-none opacity-40"}`}
          >
            <ChevronLeft className="size-4" aria-hidden />
            <span className="sr-only">Previous application</span>
          </Link>
          <Link
            aria-disabled={!next}
            href={next ? `/applications/${next.pseudonym}` : "#"}
            className={`grid size-9 place-items-center rounded-xl bg-white ${next ? "" : "pointer-events-none opacity-40"}`}
          >
            <ChevronRight className="size-4" aria-hidden />
            <span className="sr-only">Next application</span>
          </Link>
        </nav>
      </header>
      <p className="text-sm text-muted-foreground">
        {meta || "No profile data"}. Used for eligibility checks only; the model never sees it.
      </p>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <section aria-label="Proposal and reasons" className="space-y-4">
          <article data-tour="proposal" className={`rounded-[1.75rem] p-5 ${tone ? `${tone.bg} ${tone.ink}` : "bg-white"}`}>
            <p className="text-sm">Proposed decision</p>
            <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
              <h2 className="text-3xl font-semibold">{v.proposed ?? "No proposal"}</h2>
              <p className="font-display text-4xl font-semibold tabular-nums">
                {v.total ?? "–"}
                <span className="text-xl opacity-60">/{v.max_total}</span>
              </p>
            </div>
            <p className="mt-3 text-sm">{humanize(v.rule)}</p>
            {v.request_further_review && (
              <div className="mt-3 rounded-xl bg-white/70 p-3 text-sm text-ink">
                <ReviewBadge review />
                <ul className="mt-2 list-disc space-y-0.5 pl-5">
                  {v.review_reasons.map((r) => (
                    <li key={r}>{humanize(r)}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="mt-3 text-xs opacity-75">
              {v.quotes_verified} of {v.quotes_total} quotes verified word for word. Model {v.llm.model},{" "}
              {Math.round(v.llm.seconds)} s.
            </p>
          </article>

          {attention > 0 && (
            <article data-tour="to-check" className="rounded-2xl bg-white p-4">
              <h3 className="text-base font-semibold">To check</h3>
              <ul className="mt-3 space-y-2">
                {v.findings.map((f, i) => (
                  <li key={`f${i}`} className="flex gap-2 text-sm">
                    <TriangleAlert
                      className={`mt-0.5 size-4 shrink-0 ${f.severity === "alert" ? "text-destructive" : "text-waitlist-ink"}`}
                      aria-hidden
                    />
                    <span>
                      <span className="font-medium">{f.severity === "alert" ? "Alert" : "To check"}.</span> {displayText(f.message)}
                    </span>
                  </li>
                ))}
                {v.concerns.map((c, i) => (
                  <li key={`c${i}`} className="flex gap-2 text-sm">
                    <Flag className="mt-0.5 size-4 shrink-0 text-review-ink" aria-hidden />
                    <span>
                      <span className="font-medium">{c.name}</span>{" "}
                      <span className="text-muted-foreground">({c.source === "modèle" ? "raised by the model" : "raised by the checks"})</span>
                      . {displayText(c.detail)}
                    </span>
                  </li>
                ))}
              </ul>
            </article>
          )}

          <div className="space-y-3" data-tour="criteria">
            {v.criteria.map((c) => (
              <CriterionCard key={c.key} c={c} active={active === c.key} onShow={() => show(c.key)} />
            ))}
          </div>

          <article data-tour="decision-form" className="rounded-2xl bg-white p-5">
            <h3 className="text-base font-semibold">Your decision</h3>
            {data.retained && (
              <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                Recorded decision: <VerdictBadge verdict={data.retained} />
                <ReviewBadge review={data.retained_review} />
              </p>
            )}
            <div className="mt-3">
              <DecisionForm
                key={data.decisions.length}
                data={data}
                evaluator={evaluator}
                onSaved={(message) => {
                  setSaved(message);
                  reload();
                }}
              />
            </div>
            {saved && (
              <div role="status" className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-invite p-3 text-sm text-invite-ink">
                <span>{saved}</span>
                {nextPending ? (
                  <Link href={`/applications/${nextPending.pseudonym}`} className="font-medium underline underline-offset-4">
                    Next application to review: {nextPending.pseudonym}
                  </Link>
                ) : (
                  <Link href="/" className="font-medium underline underline-offset-4">
                    Every application has a decision
                  </Link>
                )}
              </div>
            )}
            {data.decisions.length > 0 && (
              <ol className="mt-4 space-y-1 border-t border-border pt-3 text-xs text-muted-foreground">
                {data.decisions.map((d) => (
                  <li key={d.id}>
                    {new Date(d.created_at).toLocaleString("en-GB")}, {d.evaluator}{" "}
                    {d.action === "validate" ? "validated" : "changed"}: {d.proposed ?? "no proposal"}
                    {d.proposed_review ? " with review" : ""} to {d.retained}
                    {d.retained_review ? " with review" : ""}
                    {d.comment ? ` (“${d.comment}”)` : ""}
                  </li>
                ))}
              </ol>
            )}
          </article>
        </section>

        <section
          aria-label="Anonymised application"
          className="space-y-3 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto lg:pr-1"
        >
          <h2 className="text-lg font-semibold">Anonymised application</h2>
          {data.dossier.texts.map((t, index) => (
            <article key={index} className="rounded-2xl bg-white p-4">
              <p className="mb-2 text-xs text-muted-foreground">
                <span className="font-medium text-ink">{where(t)}</span>
                {t.label ? `: ${t.label}` : ""}
              </p>
              <Highlighted text={t.text} marks={marks.get(index) ?? []} active={active} />
            </article>
          ))}
        </section>
      </div>
    </div>
  );
}
