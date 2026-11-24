"use client";

// Visite guidée de la session de test : étapes, résultats déclarés par l'évaluateur,
// état retenu dans ce navigateur (reprise possible après fermeture ou rechargement).
// Les textes affichés sont en anglais, comme toute la plateforme.

import { useSyncExternalStore } from "react";

import type { StepOutcome } from "@/lib/api";

export type TourPage = "any" | "list" | "application" | "log";

export interface TourStep {
  id: string;
  title: string;
  /** Ce que l'évaluateur fait sur la plateforme. */
  body: string;
  /** Ce qui doit se passer ; absent pour l'accueil et le formulaire final. */
  expect?: string;
  /** Valeur de l'attribut data-tour de l'élément à montrer. */
  anchor?: string;
  /** Message quand l'élément n'est pas à l'écran (par exemple aucun point à vérifier). */
  missing?: string;
  page: TourPage;
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Test the platform, step by step",
    body: "This tour takes you through the test session. At each step, try what it describes on the platform, then say whether it worked. Skip a step you cannot test. You can close the tour at any time and resume it from the sidebar.",
    page: "any",
  },
  {
    id: "name",
    title: "Sign with your name",
    body: "Type your name in this field and save it. It signs every decision you record.",
    expect: "Your name is still shown after you reload the page.",
    anchor: "evaluator",
    page: "any",
  },
  {
    id: "progress",
    title: "See what is left to review",
    body: "This banner counts the applications still to review and the ones already decided.",
    expect: "The count matches the list below: 40 applications in all.",
    anchor: "progress",
    page: "list",
  },
  {
    id: "filters",
    title: "Filter by proposed decision",
    body: "Click the Interview Reject card, then click it again.",
    expect: "The first click shows only Interview Reject proposals. The second click shows every application again.",
    anchor: "decision-cards",
    page: "list",
  },
  {
    id: "find",
    title: "Find an application",
    body: "Switch between To review, Decided and All. Search for a pseudonym, then sort by Alerts first.",
    expect: "Each tab, the search and the sort change the list as their names say. Applications without a total stay at the bottom.",
    anchor: "list-tools",
    page: "list",
  },
  {
    id: "open",
    title: "Open the next application",
    body: "Click Start reviewing (or Continue reviewing).",
    expect: "The first application still to review opens.",
    anchor: "start-reviewing",
    missing: "Every application already has a decision. Open one from the list instead.",
    page: "list",
  },
  {
    id: "proposal",
    title: "Read the proposed decision",
    body: "Read the decision, the total and the rule under it. When further review is requested, the reasons are listed.",
    expect: "The rule explains the decision, for example a total compared with the invitation threshold.",
    anchor: "proposal",
    page: "application",
  },
  {
    id: "flags",
    title: "Check the flagged points",
    body: "Each line is an eligibility check or a concern. Compare it with the anonymised application on the right.",
    expect: "Each flag says what was found, and the application confirms it.",
    anchor: "to-check",
    missing: "This application has no flagged point. Use the arrows at the top to open another one, or skip this step.",
    page: "application",
  },
  {
    id: "quotes",
    title: "Check a score against its quote",
    body: "On a criterion, click Show the quote in the application. Look for any card marked Score without a quote.",
    expect: "The quote is highlighted in the application and reads word for word the same. A score without a quote is clearly marked.",
    anchor: "criteria",
    page: "application",
  },
  {
    id: "decide",
    title: "Record your decision",
    body: "Validate the proposal, or change it: pick another decision and explain why. Then follow Next application to review.",
    expect: "The status becomes Validated or Modified and your decision is listed below. A change cannot be saved without a comment.",
    anchor: "decision-form",
    page: "application",
  },
  {
    id: "log",
    title: "Find your decision in the log",
    body: "Every decision is listed here with the proposal, your choice and your comment.",
    expect: "Your decision appears once, under your name. The agreement count only counts proposals validated unchanged.",
    anchor: "decision-log",
    page: "log",
  },
  {
    id: "feedback",
    title: "Send your feedback",
    body: "One last question, then send your results to the team running the test.",
    page: "any",
  },
];

export interface TourState {
  active: boolean;
  index: number;
  results: Record<string, { result: StepOutcome; note: string }>;
  ease: number | null;
  comment: string;
  sent: boolean;
}

const KEY = "visite-test";
const EVENT = "visite-test-change";
const INITIAL: TourState = { active: false, index: 0, results: {}, ease: null, comment: "", sent: false };

// useSyncExternalStore exige le même objet tant que rien ne change : cache sur le texte stocké.
let cachedRaw: string | null = null;
let cachedState: TourState = INITIAL;
let memory: string | null = null; // repli quand le stockage du navigateur est indisponible

function rawState(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return memory;
  }
}

function read(): TourState {
  const raw = rawState();
  if (raw === cachedRaw) return cachedState;
  cachedRaw = raw;
  try {
    cachedState = raw ? { ...INITIAL, ...(JSON.parse(raw) as Partial<TourState>) } : INITIAL;
  } catch {
    cachedState = INITIAL;
  }
  return cachedState;
}

function write(next: TourState) {
  const raw = JSON.stringify(next);
  memory = raw;
  try {
    window.localStorage.setItem(KEY, raw);
  } catch {
    // stockage indisponible : l'état reste en mémoire jusqu'au rechargement
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

export function useTour(): TourState {
  return useSyncExternalStore(subscribe, read, () => INITIAL);
}

export function updateTour(patch: Partial<TourState>) {
  write({ ...read(), ...patch });
}

/** Ouvre la visite : reprend là où elle s'était arrêtée, ou recommence après un envoi. */
export function startTour() {
  const state = read();
  write(state.sent ? { ...INITIAL, active: true } : { ...state, active: true });
}

export function setStepResult(id: string, result: StepOutcome, note: string) {
  const state = read();
  write({ ...state, results: { ...state.results, [id]: { result, note } } });
}
