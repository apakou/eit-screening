"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ReviewBadge, StatusBadge, VerdictBadge } from "@/components/verdict-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { type CandidateSummary, listCandidates, VERDICTS } from "@/lib/api";

type SortKey = "pseudonym" | "total" | "alerts" | "concerns" | "age";

const selectClass =
  "h-8 rounded-lg border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

export default function CandidatesPage() {
  const [rows, setRows] = useState<CandidateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState("");
  const [review, setReview] = useState("");
  const [status, setStatus] = useState("");
  const [gender, setGender] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "pseudonym", desc: false });

  useEffect(() => {
    listCandidates()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  const shown = useMemo(() => {
    if (!rows) return [];
    const filtered = rows.filter(
      (r) =>
        (!verdict || (verdict === "aucune" ? r.proposed === null : r.proposed === verdict)) &&
        (!review || r.request_further_review === (review === "oui")) &&
        (!status || r.status === status) &&
        (!gender || r.gender === gender) &&
        (!search || r.pseudonym.toLowerCase().includes(search.toLowerCase())),
    );
    const value = (r: CandidateSummary) => r[sort.key] ?? -1;
    return [...filtered].sort((a, b) => {
      const [x, y] = [value(a), value(b)];
      const order = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -order : order;
    });
  }, [rows, verdict, review, status, gender, search, sort]);

  const toggle = (key: SortKey) =>
    setSort((current) => ({ key, desc: current.key === key ? !current.desc : key !== "pseudonym" }));
  const arrow = (key: SortKey) => (sort.key === key ? (sort.desc ? " ↓" : " ↑") : "");
  const header = (key: SortKey, label: string, className = "") => (
    <TableHead className={className}>
      <button type="button" className="font-medium hover:underline" onClick={() => toggle(key)}>
        {label}
        {arrow(key)}
      </button>
    </TableHead>
  );

  const pending = rows?.filter((r) => r.status === "à traiter").length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Candidatures</h1>
          <p className="text-sm text-muted-foreground">
            {rows ? `${rows.length} candidatures, ${pending} à traiter` : "Chargement…"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <input
            aria-label="Rechercher un pseudonyme"
            placeholder="Pseudonyme"
            className={`${selectClass} w-32`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select aria-label="Décision proposée" className={selectClass} value={verdict} onChange={(e) => setVerdict(e.target.value)}>
            <option value="">Toutes les décisions</option>
            {VERDICTS.map((v) => (
              <option key={v}>{v}</option>
            ))}
            <option value="aucune">Aucune décision proposée</option>
          </select>
          <select aria-label="Revue complémentaire" className={selectClass} value={review} onChange={(e) => setReview(e.target.value)}>
            <option value="">Revue : toutes</option>
            <option value="oui">Revue demandée</option>
            <option value="non">Sans revue</option>
          </select>
          <select aria-label="Statut" className={selectClass} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Tous les statuts</option>
            <option>à traiter</option>
            <option>validé</option>
            <option>modifié</option>
          </select>
          <select aria-label="Genre" className={selectClass} value={gender} onChange={(e) => setGender(e.target.value)}>
            <option value="">Tous les genres</option>
            <option value="Female">Femme</option>
            <option value="Male">Homme</option>
          </select>
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
          Impossible de joindre l&apos;API ({error}). Vérifier que « eit-api » tourne.
        </p>
      )}

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              {header("pseudonym", "Pseudonyme")}
              <TableHead>Décision proposée</TableHead>
              {header("total", "Total", "text-right")}
              {header("alerts", "Alertes", "text-right")}
              {header("concerns", "Concerns", "text-right")}
              <TableHead className="text-right">Citations vérifiées</TableHead>
              {header("age", "Âge", "text-right")}
              <TableHead>Nationalité</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead>Décision retenue</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((r) => (
              <TableRow key={r.pseudonym}>
                <TableCell>
                  <Link className="font-mono text-primary underline-offset-4 hover:underline" href={`/candidats/${r.pseudonym}`}>
                    {r.pseudonym}
                  </Link>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    <VerdictBadge verdict={r.proposed} />
                    <ReviewBadge review={r.request_further_review} />
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {r.total ?? "–"} / {r.max_total}
                </TableCell>
                <TableCell className={`text-right tabular-nums ${r.alerts ? "font-semibold text-destructive" : ""}`}>
                  {r.alerts}
                </TableCell>
                <TableCell className="text-right tabular-nums">{r.concerns}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {r.quotes_verified} / {r.quotes_total}
                </TableCell>
                <TableCell className="text-right tabular-nums">{r.age ?? "–"}</TableCell>
                <TableCell>{r.citizenship ?? "–"}</TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                </TableCell>
                <TableCell>
                  {r.retained ? (
                    <div className="flex flex-wrap gap-1">
                      <VerdictBadge verdict={r.retained} />
                      <ReviewBadge review={r.retained_review} />
                    </div>
                  ) : (
                    "–"
                  )}
                </TableCell>
              </TableRow>
            ))}
            {rows && shown.length === 0 && (
              <TableRow>
                <TableCell colSpan={10} className="py-8 text-center text-muted-foreground">
                  Aucune candidature ne correspond aux filtres.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground">
        Genre, âge et nationalité servent aux filtres et aux contrôles d&apos;éligibilité ; ils ne sont jamais envoyés au
        modèle de langage.
      </p>
    </div>
  );
}
