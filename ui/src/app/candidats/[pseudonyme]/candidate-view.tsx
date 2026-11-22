"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { StatusBadge, VerdictBadge } from "@/components/verdict-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  type CandidateDetail,
  type CriterionResult,
  type DossierText,
  getCandidate,
  postDecision,
  SECTION_LABELS,
  VERDICTS,
  type VerdictLabel,
} from "@/lib/api";

interface Mark {
  start: number;
  end: number;
  key: string;
}

function where(text: DossierText): string {
  const parts = [SECTION_LABELS[text.section] ?? text.section];
  if (text.page) parts.push(`page ${text.page}`);
  if (text.start !== null && text.end !== null) parts.push(`${text.start.toFixed(1)}–${text.end.toFixed(1)} s`);
  return parts.join(" · ");
}

function Highlighted({ text, marks, active }: { text: string; marks: Mark[]; active: string | null }) {
  const sorted = [...marks].sort((a, b) => a.start - b.start);
  const pieces: React.ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((mark, index) => {
    if (mark.start < cursor) return; // chevauchement : la première citation l'emporte
    pieces.push(text.slice(cursor, mark.start));
    pieces.push(
      <mark
        key={index}
        id={`citation-${mark.key}`}
        className={`rounded px-0.5 ${
          mark.key === active ? "bg-amber-300 text-foreground dark:bg-amber-600" : "bg-amber-100 text-foreground dark:bg-amber-900/60"
        }`}
      >
        {text.slice(mark.start, mark.end)}
      </mark>,
    );
    cursor = mark.end;
  });
  pieces.push(text.slice(cursor));
  return <p className="whitespace-pre-wrap text-sm leading-relaxed">{pieces}</p>;
}

function CriterionCard({ c, active, onShow }: { c: CriterionResult; active: boolean; onShow: () => void }) {
  return (
    <div className={`rounded-lg border p-3 ${active ? "border-amber-400" : ""}`}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium">{c.name}</h3>
        <span className="tabular-nums text-sm font-semibold">
          {c.score} / {c.max_points}
        </span>
      </div>
      <p className="mt-1 text-sm">{c.reason}</p>
      {c.quote ? (
        <div className="mt-2 space-y-1">
          <blockquote className="border-l-2 pl-2 text-sm italic text-muted-foreground">« {c.quote} »</blockquote>
          {c.quote_verified ? (
            <Button variant="link" size="sm" className="h-auto p-0" onClick={onShow}>
              Citation vérifiée : voir dans le dossier
            </Button>
          ) : (
            <Badge variant="destructive">Citation introuvable mot pour mot : ce n&apos;est pas une preuve</Badge>
          )}
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">Aucune citation fournie.</p>
      )}
    </div>
  );
}

export function CandidateView({ pseudonym }: { pseudonym: string }) {
  const [data, setData] = useState<CandidateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [evaluator, setEvaluator] = useState("");
  const [modifying, setModifying] = useState(false);
  const [retained, setRetained] = useState<VerdictLabel | "">("");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(
    () =>
      getCandidate(pseudonym)
        .then(setData)
        .catch((e: Error) => setError(e.message)),
    [pseudonym],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  // Nom de l'évaluateur retenu dans ce navigateur, proposé quand le champ est vide.
  const recallEvaluator = () => {
    if (evaluator) return;
    try {
      setEvaluator(window.localStorage.getItem("evaluateur") ?? "");
    } catch {
      // stockage indisponible : le nom sera saisi à chaque fois
    }
  };

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

  const submit = async (action: "validate" | "modify") => {
    if (!data) return;
    setSaving(true);
    setMessage(null);
    try {
      try {
        window.localStorage.setItem("evaluateur", evaluator);
      } catch {
        // sans effet
      }
      await postDecision(data.pseudonym, {
        evaluator,
        action,
        ...(action === "modify" ? { retained: retained || undefined, comment } : { comment }),
      });
      setModifying(false);
      setComment("");
      setRetained("");
      setMessage(action === "validate" ? "Verdict validé." : "Verdict modifié.");
      await reload();
    } catch (e) {
      setMessage(`Décision refusée : ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
        Impossible de charger {pseudonym} ({error}). <Link href="/" className="underline">Retour à la liste</Link>
      </p>
    );
  }
  if (!data) return <p className="text-sm text-muted-foreground">Chargement…</p>;

  const v = data.verdict;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-sm text-muted-foreground hover:underline">
            ← Candidatures
          </Link>
          <h1 className="font-mono text-xl font-semibold">{data.pseudonym}</h1>
          <StatusBadge status={data.status} />
        </div>
        <p className="text-sm text-muted-foreground">
          {data.gender ?? "?"} · {data.age ?? "?"} ans · {data.citizenship ?? "?"} (filtres, jamais montrés au modèle)
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <section aria-label="Verdict et raisons" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                Verdict proposé <VerdictBadge verdict={v.proposed} />
                <span className="ml-auto tabular-nums">
                  {v.total ?? "–"} / {v.max_total}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">{v.rule}</p>
              <p className="text-xs text-muted-foreground">
                Citations vérifiées mot pour mot : {v.quotes_verified} / {v.quotes_total} · modèle {v.llm.model},{" "}
                {v.llm.attempts} essai(s), {Math.round(v.llm.seconds)} s
              </p>
              {(v.findings.length > 0 || v.concerns.length > 0) && (
                <ul className="space-y-1 text-sm">
                  {v.findings.map((f, i) => (
                    <li key={`f${i}`} className="flex gap-2">
                      <Badge variant={f.severity === "alert" ? "destructive" : "outline"}>
                        {f.severity === "alert" ? "alerte" : "à vérifier"}
                      </Badge>
                      <span>{f.message}</span>
                    </li>
                  ))}
                  {v.concerns.map((c, i) => (
                    <li key={`c${i}`} className="flex gap-2">
                      <Badge variant="secondary">Concern</Badge>
                      <span>
                        {c.name} ({c.source}) : {c.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <div className="space-y-2">
            {v.criteria.map((c) => (
              <CriterionCard key={c.key} c={c} active={active === c.key} onShow={() => show(c.key)} />
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Décision de l&apos;évaluateur</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <Label htmlFor="evaluateur">Évaluateur</Label>
                <Input
                  id="evaluateur"
                  value={evaluator}
                  onFocus={recallEvaluator}
                  onChange={(e) => setEvaluator(e.target.value)}
                  placeholder="Votre nom"
                />
              </div>
              {!modifying ? (
                <div className="flex flex-wrap gap-2">
                  <Button disabled={!evaluator.trim() || saving} onClick={() => submit("validate")}>
                    Valider « {v.proposed} »
                  </Button>
                  <Button variant="outline" disabled={saving} onClick={() => setModifying(true)}>
                    Modifier
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label htmlFor="verdict-retenu">Verdict retenu</Label>
                    <select
                      id="verdict-retenu"
                      className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm"
                      value={retained}
                      onChange={(e) => setRetained(e.target.value as VerdictLabel)}
                    >
                      <option value="">Choisir…</option>
                      {VERDICTS.filter((x) => x !== v.proposed).map((x) => (
                        <option key={x}>{x}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="commentaire">Pourquoi ? (obligatoire)</Label>
                    <Textarea id="commentaire" value={comment} onChange={(e) => setComment(e.target.value)} />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      disabled={!evaluator.trim() || !retained || !comment.trim() || saving}
                      onClick={() => submit("modify")}
                    >
                      Enregistrer la modification
                    </Button>
                    <Button variant="ghost" onClick={() => setModifying(false)}>
                      Annuler
                    </Button>
                  </div>
                </div>
              )}
              {message && <p className="text-sm" role="status">{message}</p>}
              {data.decisions.length > 0 && (
                <ul className="space-y-1 border-t pt-2 text-xs text-muted-foreground">
                  {data.decisions.map((d) => (
                    <li key={d.id}>
                      {new Date(d.created_at).toLocaleString("fr-FR")} · {d.evaluator} ·{" "}
                      {d.action === "validate" ? "a validé" : "a modifié"} : {d.proposed} → {d.retained}
                      {d.comment ? ` (« ${d.comment} »)` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </section>

        <section aria-label="Dossier anonymisé" className="space-y-3 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
          <h2 className="text-sm font-medium text-muted-foreground">Dossier anonymisé</h2>
          {data.dossier.texts.map((t, index) => (
            <article key={index} className="rounded-lg border p-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                {where(t)}
                {t.label ? ` — ${t.label}` : ""}
              </p>
              <Highlighted text={t.text} marks={marks.get(index) ?? []} active={active} />
            </article>
          ))}
        </section>
      </div>
    </div>
  );
}
