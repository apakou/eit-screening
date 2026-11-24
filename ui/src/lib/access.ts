"use client";

// Code d'accès partagé avec les testeurs quand l'API est en ligne (variable EIT_ACCESS_CODE côté API).
// Saisi une fois, retenu dans ce navigateur. Ce n'est pas une identité : le nom de l'évaluateur reste à part.

import { useSyncExternalStore } from "react";

const KEY = "code-acces";
const EVENT = "code-acces-change";
let memory = "";

export function readAccessCode(): string {
  try {
    return window.localStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setAccessCode(code: string) {
  memory = code;
  try {
    window.localStorage.setItem(KEY, code);
  } catch {
    // stockage indisponible : le code reste valable jusqu'au rechargement
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

export function useAccessCode(): string {
  return useSyncExternalStore(subscribe, readAccessCode, () => "");
}
