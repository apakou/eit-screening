"use client";

// Nom de l'évaluateur, saisi une fois et retenu dans ce navigateur.
// Lu avec useSyncExternalStore : pas de setState dans un effet, pas d'écart d'hydratation.

import { useSyncExternalStore } from "react";

const KEY = "evaluateur";
const EVENT = "evaluateur-change";

function read(): string {
  try {
    return window.localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

export function setEvaluator(name: string) {
  try {
    window.localStorage.setItem(KEY, name);
  } catch {
    // stockage indisponible : le nom reste valable jusqu'au rechargement
  }
  window.dispatchEvent(new Event(EVENT));
}

export function useEvaluator(): string {
  return useSyncExternalStore(subscribe, read, () => "");
}
