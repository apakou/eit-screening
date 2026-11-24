"use client";

import { ClipboardList, History, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState } from "react";

import { setEvaluator, useEvaluator } from "@/lib/evaluator";

const NAV = [
  { href: "/", label: "Applications", icon: ClipboardList, match: (p: string) => p === "/" || p.startsWith("/applications") },
  { href: "/decisions", label: "Decision log", icon: History, match: (p: string) => p.startsWith("/decisions") },
];

function EvaluatorField() {
  const evaluator = useEvaluator();
  const [draft, setDraft] = useState<string | null>(null);
  const editing = draft !== null || !evaluator;

  if (!editing) {
    return (
      <div className="flex items-center gap-3 rounded-2xl bg-white p-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-review text-sm font-semibold text-review-ink">
          {evaluator.slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{evaluator}</p>
          <button
            type="button"
            className="text-xs text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => setDraft(evaluator)}
          >
            Change name
          </button>
        </div>
      </div>
    );
  }
  return (
    <form
      className="space-y-2 rounded-2xl bg-white p-3"
      onSubmit={(e) => {
        e.preventDefault();
        const name = (draft ?? "").trim();
        if (name) {
          setEvaluator(name);
          setDraft(null);
        }
      }}
    >
      <label htmlFor="nom-evaluateur" className="flex items-center gap-2 text-sm font-medium">
        <UserRound className="size-4" aria-hidden /> Your name
      </label>
      <input
        id="nom-evaluateur"
        value={draft ?? ""}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="It signs your decisions"
        className="h-9 w-full rounded-lg border border-input bg-paper px-2 text-sm"
      />
      <button type="submit" className="h-8 w-full rounded-lg bg-ink text-sm font-medium text-white disabled:opacity-40" disabled={!(draft ?? "").trim()}>
        Save
      </button>
    </form>
  );
}

function NavLinks({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Main navigation" className="flex gap-1 lg:flex-col">
      {NAV.map(({ href, label, icon: Icon, match }) => {
        const active = match(pathname);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors ${
              active ? "bg-ink text-white" : "text-foreground hover:bg-white"
            }`}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

// Next.js 16 : usePathname() doit être lu dans une frontière <Suspense>.
function ActiveNav() {
  return <NavLinks pathname={usePathname()} />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full lg:grid lg:grid-cols-[17rem_1fr]">
      <aside className="border-b border-border bg-[#f4eee4] lg:sticky lg:top-0 lg:h-screen lg:border-r lg:border-b-0">
        <div className="flex h-full flex-col gap-6 p-4 lg:p-5">
          <Link href="/" className="flex items-center gap-3">
            <span aria-hidden className="grid size-10 place-items-center rounded-2xl bg-ink font-display text-lg font-bold text-white">
              M
            </span>
            <span className="leading-tight">
              <span className="block font-display text-base font-semibold">MEST pre-screening</span>
              <span className="block text-xs text-muted-foreground">AI Startup Program, class of 2027</span>
            </span>
          </Link>
          <Suspense fallback={<NavLinks pathname="" />}>
            <ActiveNav />
          </Suspense>
          <div className="mt-auto hidden space-y-3 lg:block">
            <EvaluatorField />
            <p className="px-1 text-xs leading-relaxed text-muted-foreground">
              The system proposes; you decide. Each decision keeps the proposal and your choice.
            </p>
          </div>
        </div>
      </aside>
      <main className="mx-auto w-full max-w-7xl px-4 py-6 lg:px-8 lg:py-8">
        <div className="mb-6 lg:hidden">
          <EvaluatorField />
        </div>
        {children}
      </main>
    </div>
  );
}
