"use client";

// Visite guidée de la session de test : une bulle ancrée sur l'élément décrit,
// « Step N of M », points de progression, Skip et Next. À chaque étape,
// l'évaluateur dit si ce qui doit se passer s'est passé ; la dernière étape
// envoie ces résultats et son avis à l'API (table tour_feedback).

import { ArrowRight, Check, LifeBuoy, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { listCandidates, postFeedback, type StepOutcome, type StepResult } from "@/lib/api";
import { useEvaluator } from "@/lib/evaluator";
import { setStepResult, startTour, TOUR_STEPS, type TourPage, updateTour, useTour } from "@/lib/tour";

const GAP = 14; // écart entre l'élément montré et la bulle
const MARGIN = 16; // marge minimale au bord de l'écran
const PAD = 6; // débord de la zone éclairée autour de l'élément

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

function findAnchor(name: string | undefined): HTMLElement | null {
  if (!name) return null;
  // Le même repère peut exister deux fois (barre latérale et version mobile) : on prend celui qui est affiché.
  for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`)) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return el;
  }
  return null;
}

function sameBox(a: Box | null, b: Box | null) {
  return a === b || (!!a && !!b && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height);
}

function onPage(page: TourPage, pathname: string) {
  if (page === "list") return pathname === "/";
  if (page === "application") return pathname.startsWith("/applications/");
  if (page === "log") return pathname.startsWith("/decisions");
  return true;
}

/** Bouton de la barre latérale qui ouvre ou reprend la visite. */
export function TourLauncher() {
  const tour = useTour();
  const started = !tour.active && Object.keys(tour.results).length > 0 && !tour.sent;
  return (
    <button
      type="button"
      onClick={startTour}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm hover:bg-white"
    >
      <LifeBuoy className="size-4" aria-hidden />
      <span className="flex-1">{started ? "Resume test session" : "Test session"}</span>
      {(started || tour.active) && (
        <span className="rounded-full bg-review px-2 text-xs text-review-ink tabular-nums">
          {tour.index + 1}/{TOUR_STEPS.length}
        </span>
      )}
    </button>
  );
}

export function TestTour() {
  const tour = useTour();
  const evaluator = useEvaluator();
  const pathname = usePathname();
  const router = useRouter();
  const step = TOUR_STEPS[Math.min(tour.index, TOUR_STEPS.length - 1)];
  const last = tour.index === TOUR_STEPS.length - 1;

  const [anchor, setAnchor] = useState<Box | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [popHeight, setPopHeight] = useState(0);
  const popRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const scrolledFor = useRef<string | null>(null);

  // Mène l'évaluateur sur le bon écran en entrant dans une étape, une seule fois :
  // l'action demandée peut elle-même changer d'écran (Start reviewing ouvre un dossier).
  const routedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!tour.active) {
      routedFor.current = null;
      return;
    }
    if (routedFor.current === step.id) return;
    routedFor.current = step.id;
    if (onPage(step.page, pathname)) return;
    if (step.page === "list") router.push("/");
    else if (step.page === "log") router.push("/decisions");
    else if (step.page === "application") {
      listCandidates()
        .then((rows) => {
          const sorted = [...rows].sort((a, b) => a.pseudonym.localeCompare(b.pseudonym));
          const target = sorted.find((r) => r.status === "pending") ?? sorted[0];
          if (target) router.push(`/applications/${target.pseudonym}`);
        })
        .catch(() => {
          // API indisponible : l'écran de la liste affiche déjà l'erreur
        });
    }
  }, [tour.active, step, pathname, router]);

  // Suit la position de l'élément montré (chargement des données, défilement, redimensionnement).
  useEffect(() => {
    if (!tour.active) return;
    const measure = () => {
      setViewport((v) => (v.width === window.innerWidth && v.height === window.innerHeight ? v : { width: window.innerWidth, height: window.innerHeight }));
      const el = findAnchor(step.anchor);
      if (el && scrolledFor.current !== step.id) {
        scrolledFor.current = step.id;
        const r = el.getBoundingClientRect();
        if (r.top < 0 || r.bottom > window.innerHeight) {
          const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
          el.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? "start" : "center", behavior: reduce ? "auto" : "smooth" });
        }
      }
      const r = el?.getBoundingClientRect();
      const box = r ? { top: r.top, left: r.left, width: r.width, height: r.height } : null;
      setAnchor((prev) => (sameBox(prev, box) ? prev : box));
      const h = popRef.current?.offsetHeight ?? 0;
      setPopHeight((prev) => (prev === h ? prev : h));
    };
    measure();
    const timer = window.setInterval(measure, 200);
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [tour.active, step]);

  // Le lecteur d'écran et le clavier suivent la bulle à chaque étape.
  useLayoutEffect(() => {
    if (tour.active) titleRef.current?.focus({ preventScroll: true });
  }, [tour.active, tour.index]);

  const close = useCallback(() => updateTour({ active: false }), []);
  useEffect(() => {
    if (!tour.active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tour.active, close]);

  if (!tour.active) return null;

  const go = (index: number) => updateTour({ index: Math.max(0, Math.min(TOUR_STEPS.length - 1, index)) });
  const current = tour.results[step.id];
  const needsAnswer = !!step.expect;
  const answered = !!current && (current.result !== "failed" || current.note.trim().length > 0);
  const missing = !!step.anchor && !anchor && onPage(step.page, pathname);

  // Placement de la bulle : à côté de l'élément s'il y a la place, sinon dessous, sinon dessus.
  const narrow = viewport.width < 640;
  const width = Math.min(384, viewport.width - 2 * MARGIN);
  let style: React.CSSProperties;
  if (narrow || !anchor) {
    style = narrow
      ? { left: MARGIN, right: MARGIN, bottom: `calc(${MARGIN}px + env(safe-area-inset-bottom, 0px))` }
      : { left: (viewport.width - width) / 2, top: Math.max(MARGIN, (viewport.height - popHeight) / 2), width };
  } else {
    const below = anchor.top + anchor.height + PAD + GAP;
    const above = anchor.top - PAD - GAP - popHeight;
    const right = anchor.left + anchor.width + PAD + GAP;
    const clampLeft = (x: number) => Math.max(MARGIN, Math.min(x, viewport.width - width - MARGIN));
    const clampTop = (y: number) => Math.max(MARGIN, Math.min(y, viewport.height - popHeight - MARGIN));
    const left = anchor.left - PAD - GAP - width;
    // À côté : centrée sur la partie visible de l'élément.
    const visibleTop = Math.max(anchor.top, 0);
    const visibleBottom = Math.min(anchor.top + anchor.height, viewport.height);
    const besideTop = clampTop((visibleTop + visibleBottom) / 2 - popHeight / 2);
    if (right + width + MARGIN <= viewport.width) {
      style = { left: right, top: besideTop, width };
    } else if (left >= MARGIN) {
      style = { left, top: besideTop, width };
    } else if (below + popHeight + MARGIN <= viewport.height) {
      style = { left: clampLeft(anchor.left), top: below, width };
    } else if (above >= MARGIN) {
      style = { left: clampLeft(anchor.left), top: above, width };
    } else {
      // Élément plus haut que l'écran : la bulle se pose dans son coin inférieur droit.
      style = { left: clampLeft(anchor.left + anchor.width - width - GAP), top: clampTop(viewport.height - popHeight - MARGIN), width };
    }
  }

  const choose = (result: StepOutcome) => setStepResult(step.id, result, result === "failed" ? current?.note ?? "" : "");

  return (
    <>
      {/* Zone éclairée : l'ombre assombrit le reste de l'écran sans bloquer les clics, l'évaluateur doit pouvoir agir. */}
      {anchor ? (
        <div
          aria-hidden
          className="pointer-events-none fixed z-40 rounded-2xl ring-2 ring-white transition-all duration-200 motion-reduce:transition-none"
          style={{
            top: anchor.top - PAD,
            left: anchor.left - PAD,
            width: anchor.width + 2 * PAD,
            height: anchor.height + 2 * PAD,
            boxShadow: "0 0 0 9999px rgba(22, 22, 26, 0.45)",
          }}
        />
      ) : (
        <div aria-hidden className="pointer-events-none fixed inset-0 z-40 bg-[rgba(22,22,26,0.45)]" />
      )}

      <div
        ref={popRef}
        role="dialog"
        aria-modal="false"
        aria-labelledby="tour-title"
        className="fixed z-50 overflow-y-auto overscroll-contain rounded-3xl bg-ink p-5 text-white shadow-[0_24px_60px_rgba(0,0,0,0.35)]"
        style={{ ...style, maxHeight: `calc(100dvh - ${2 * MARGIN}px)` }}
      >
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white/10">
            <LifeBuoy className="size-4" aria-hidden />
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="text-xs text-white/70">Test session</p>
            <p className="text-xs text-white/50 tabular-nums">
              Step {tour.index + 1} of {TOUR_STEPS.length}
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            className="grid size-8 place-items-center rounded-full text-white/70 hover:bg-white/10 hover:text-white"
          >
            <X className="size-4" aria-hidden />
            <span className="sr-only">Close the tour (you can resume it from the sidebar)</span>
          </button>
        </div>

        <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="mt-4 text-lg font-semibold outline-none">
          {step.title}
        </h2>
        <p className="mt-1.5 text-sm leading-relaxed text-white/85">{step.body}</p>

        {missing && step.missing && (
          <p className="mt-3 rounded-xl bg-waitlist/90 p-2.5 text-sm text-waitlist-ink">{step.missing}</p>
        )}

        {needsAnswer && (
          <div className="mt-4 space-y-2">
            <p className="text-xs font-medium text-white/60">What should happen</p>
            <p className="text-sm leading-relaxed">{step.expect}</p>
            <div role="radiogroup" aria-label="Did it work?" className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                role="radio"
                aria-checked={current?.result === "worked"}
                onClick={() => choose("worked")}
                className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm ring-1 ring-white/25 hover:ring-white/60 aria-checked:bg-invite aria-checked:text-invite-ink aria-checked:ring-0"
              >
                <Check className="size-3.5" aria-hidden /> It worked
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={current?.result === "failed"}
                onClick={() => choose("failed")}
                className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm ring-1 ring-white/25 hover:ring-white/60 aria-checked:bg-reject aria-checked:text-reject-ink aria-checked:ring-0"
              >
                <X className="size-3.5" aria-hidden /> It didn&apos;t
              </button>
            </div>
            {current?.result === "failed" && (
              <label className="block space-y-1 pt-1">
                <span className="text-xs font-medium text-white/60">What happened instead?</span>
                <textarea
                  autoFocus
                  rows={3}
                  value={current.note}
                  onChange={(e) => setStepResult(step.id, "failed", e.target.value)}
                  placeholder="What you did, what you saw, and the pseudonym if it concerns one application."
                  className="w-full rounded-xl bg-white/10 p-2.5 text-sm text-white placeholder:text-white/40 focus:outline-2 focus:outline-white"
                />
              </label>
            )}
          </div>
        )}

        {last && <FeedbackForm evaluator={evaluator} onEditName={() => go(1)} />}

        <Dots index={tour.index} onGo={go} />

        <div className="mt-4 flex items-center justify-between gap-3">
          {tour.index === 0 ? (
            <button type="button" onClick={close} className="px-1 py-2 text-sm text-white/80 hover:text-white">
              Not now
            </button>
          ) : !last ? (
            <button
              type="button"
              onClick={() => {
                if (needsAnswer) setStepResult(step.id, "skipped", "");
                go(tour.index + 1);
              }}
              className="px-1 py-2 text-sm text-white/80 hover:text-white"
            >
              Skip
            </button>
          ) : (
            <span />
          )}
          {!last && (
            <button
              type="button"
              disabled={needsAnswer && !answered}
              onClick={() => go(tour.index + 1)}
              className="inline-flex h-10 items-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-ink hover:bg-paper disabled:opacity-40"
            >
              {tour.index === 0 ? "Start" : "Next"} <ArrowRight className="size-4" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </>
  );
}

function Dots({ index, onGo }: { index: number; onGo: (i: number) => void }) {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-1.5" aria-label="Steps">
      {TOUR_STEPS.map((s, i) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onGo(i)}
          aria-label={`Go to step ${i + 1}: ${s.title}`}
          aria-current={i === index ? "step" : undefined}
          className={`h-1.5 rounded-full transition-all motion-reduce:transition-none ${
            i === index ? "w-6 bg-white" : i < index ? "w-1.5 bg-white/70" : "w-1.5 bg-white/25 hover:bg-white/50"
          }`}
        />
      ))}
    </div>
  );
}

function FeedbackForm({ evaluator, onEditName }: { evaluator: string; onEditName: () => void }) {
  const tour = useTour();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const asked = TOUR_STEPS.filter((s) => s.expect);
  const steps: StepResult[] = asked.map((s) => ({
    step: s.id,
    title: s.title,
    result: tour.results[s.id]?.result ?? "skipped",
    note: tour.results[s.id]?.note ?? "",
  }));
  const count = (r: StepOutcome) => steps.filter((s) => s.result === r).length;
  const incomplete = steps.filter((s) => s.result === "failed" && !s.note.trim());

  if (tour.sent) {
    return (
      <div className="mt-4 space-y-3">
        <p className="rounded-xl bg-invite p-3 text-sm text-invite-ink">Thank you. Your feedback is saved for the team running the test.</p>
        <button
          type="button"
          onClick={() => updateTour({ active: false })}
          className="inline-flex h-10 items-center rounded-full bg-white px-5 text-sm font-semibold text-ink hover:bg-paper"
        >
          Close
        </button>
      </div>
    );
  }

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      await postFeedback({ evaluator, steps, ease: tour.ease, comment: tour.comment });
      updateTour({ sent: true });
    } catch (e) {
      setError(`Feedback not sent: ${(e as Error).message}. Your answers are kept; try again.`);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="mt-4 space-y-4">
      <p className="text-sm text-white/85 tabular-nums">
        {count("worked")} worked, {count("failed")} didn&apos;t, {count("skipped")} skipped.
      </p>
      <fieldset>
        <legend className="text-sm font-medium">How easy was the platform to use?</legend>
        <div className="mt-2 flex items-center gap-1.5">
          <span className="text-xs text-white/60">Hard</span>
          {[1, 2, 3, 4, 5].map((n) => (
            <label
              key={n}
              className={`grid size-9 cursor-pointer place-items-center rounded-full text-sm tabular-nums ring-1 has-focus-visible:outline-2 has-focus-visible:outline-white ${
                tour.ease === n ? "bg-white text-ink ring-white" : "ring-white/25 hover:ring-white/60"
              }`}
            >
              <input type="radio" name="tour-ease" value={n} checked={tour.ease === n} onChange={() => updateTour({ ease: n })} className="sr-only" />
              {n}
            </label>
          ))}
          <span className="text-xs text-white/60">Easy</span>
        </div>
      </fieldset>
      <label className="block space-y-1">
        <span className="text-sm font-medium">What would you change first?</span>
        <textarea
          rows={3}
          value={tour.comment}
          onChange={(e) => updateTour({ comment: e.target.value })}
          placeholder="Optional"
          className="w-full rounded-xl bg-white/10 p-2.5 text-sm text-white placeholder:text-white/40 focus:outline-2 focus:outline-white"
        />
      </label>
      {!evaluator && (
        <p className="rounded-xl bg-waitlist p-2.5 text-sm text-waitlist-ink">
          Your name is missing.{" "}
          <button type="button" onClick={onEditName} className="font-medium underline underline-offset-4">
            Go back to step 2
          </button>{" "}
          to enter it.
        </p>
      )}
      {incomplete.length > 0 && (
        <p className="rounded-xl bg-waitlist p-2.5 text-sm text-waitlist-ink">
          Say what happened for: {incomplete.map((s) => s.title).join(", ")}.
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-reject p-2.5 text-sm text-reject-ink">
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <button
          type="button"
          disabled={!evaluator || incomplete.length > 0 || sending}
          onClick={send}
          className="inline-flex h-10 items-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-ink hover:bg-paper disabled:opacity-40"
        >
          {sending ? "Sending…" : "Send feedback"} <ArrowRight className="size-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}
