"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ReviewBadge, VerdictBadge } from "@/components/verdict-badge";
import { type Decision, listDecisions } from "@/lib/api";

export default function JournalPage() {
  const [rows, setRows] = useState<Decision[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDecisions()
      .then((list) => setRows([...list].reverse()))
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <p role="alert" className="rounded-2xl bg-reject p-4 text-sm text-reject-ink">
        The API is not responding ({error}). Start “eit-api”, then reload the page.
      </p>
    );
  }
  if (!rows) return <p className="text-sm text-muted-foreground">Loading the decision log…</p>;

  // Dernière décision de chaque dossier : c'est elle qui compte pour l'alignement.
  const latest = new Map<string, Decision>();
  [...rows].reverse().forEach((d) => latest.set(d.pseudonym, d));
  const decided = [...latest.values()];
  const validated = decided.filter((d) => d.action === "validate").length;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">Decision log</h1>
        <p className="max-w-2xl text-muted-foreground">
          Each entry keeps the system&apos;s proposal and the decision retained. The log is never rewritten: a new
          decision is added after the previous one.
        </p>
      </header>

      {decided.length > 0 && (
        <section aria-label="Agreement" className="rounded-[1.75rem] bg-white p-6">
          <p className="font-display text-4xl font-semibold tabular-nums">
            {validated} <span className="text-xl text-muted-foreground">of {decided.length}</span>
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            applications where the proposal was validated unchanged (latest decision for each application).
          </p>
        </section>
      )}

      {rows.length === 0 ? (
        <p className="rounded-2xl bg-white p-6 text-sm">
          No decisions yet. Open an application from the{" "}
          <Link href="/" className="underline underline-offset-4">
            applications list
          </Link>{" "}
          to validate or change its proposal.
        </p>
      ) : (
        <ol className="space-y-2">
          {rows.map((d) => (
            <li key={d.id} className="grid gap-2 rounded-2xl bg-white px-4 py-3 md:grid-cols-[10rem_1fr_12rem] md:items-center">
              <span>
                <Link href={`/applications/${d.pseudonym}`} className="font-medium tabular-nums underline-offset-4 hover:underline">
                  {d.pseudonym}
                </Link>
                <span className="block text-xs text-muted-foreground">{new Date(d.created_at).toLocaleString("en-GB")}</span>
              </span>
              <span className="flex flex-wrap items-center gap-1 text-sm">
                <VerdictBadge verdict={d.proposed} />
                <ReviewBadge review={d.proposed_review} />
                <span className="px-1 text-muted-foreground">{d.action === "validate" ? "validated" : "changed to"}</span>
                {d.action === "modify" && (
                  <>
                    <VerdictBadge verdict={d.retained} />
                    <ReviewBadge review={d.retained_review} />
                  </>
                )}
                {d.comment && <span className="w-full text-muted-foreground">“{d.comment}”</span>}
              </span>
              <span className="text-sm md:text-right">{d.evaluator}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
