"use client";

// Écran du code d'accès. Il ne s'affiche que si l'API en exige un (version en ligne) ;
// en local, sans EIT_ACCESS_CODE, l'interface s'ouvre directement.

import { KeyRound } from "lucide-react";
import { useEffect, useState } from "react";

import { setAccessCode, useAccessCode } from "@/lib/access";
import { ACCESS_DENIED_EVENT, AccessCodeError, checkAccess } from "@/lib/api";

type Gate = "checking" | "open" | "locked";

export function AccessGate({ children }: { children: React.ReactNode }) {
  const code = useAccessCode();
  const [gate, setGate] = useState<Gate>("checking");
  const [draft, setDraft] = useState("");
  const [wrong, setWrong] = useState(false);

  useEffect(() => {
    let alive = true;
    checkAccess()
      .then(() => alive && setGate("open"))
      .catch((e) => {
        if (!alive) return;
        if (e instanceof AccessCodeError) {
          setWrong(code !== "");
          setGate("locked");
        } else {
          setGate("open"); // API injoignable : chaque écran affiche déjà son erreur
        }
      });
    return () => {
      alive = false;
    };
  }, [code]);

  useEffect(() => {
    const lock = () => setGate("locked");
    window.addEventListener(ACCESS_DENIED_EVENT, lock);
    return () => window.removeEventListener(ACCESS_DENIED_EVENT, lock);
  }, []);

  if (gate === "open") return <>{children}</>;
  if (gate === "checking") return <p className="p-8 text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="grid min-h-screen place-items-center bg-paper px-4">
      <form
        className="w-full max-w-sm space-y-4 rounded-[1.75rem] bg-white p-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) {
            setGate("checking");
            setAccessCode(draft.trim());
          }
        }}
      >
        <span aria-hidden className="grid size-10 place-items-center rounded-2xl bg-ink text-white">
          <KeyRound className="size-5" />
        </span>
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">MEST pre-screening</h1>
          <p className="text-sm text-muted-foreground">Enter the access code given by the team running the test session.</p>
        </div>
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Access code</span>
          <input
            type="password"
            autoComplete="off"
            autoFocus
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setWrong(false);
            }}
            className="h-10 w-full rounded-xl border border-input bg-paper px-3"
          />
        </label>
        {wrong && (
          <p role="alert" className="rounded-xl bg-reject p-2.5 text-sm text-reject-ink">
            This code is not valid. Check it with the test organiser.
          </p>
        )}
        <button type="submit" disabled={!draft.trim()} className="h-10 w-full rounded-xl bg-ink text-sm font-medium text-white disabled:opacity-40">
          Open the platform
        </button>
      </form>
    </div>
  );
}
