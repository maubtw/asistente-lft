"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { Modo } from "./api";

const KEY = "asistente-lft:modo";
const listeners = new Set<() => void>();

function read(): Modo {
  try {
    const value = localStorage.getItem(KEY);
    return value === "ligero" ? "ligero" : "completo";
  } catch {
    return "completo"; // almacenamiento no disponible
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Tipo de respuesta recordado por navegador (conveniencia; si falla, vale "completo"). */
export function useStoredMode(): [Modo, (mode: Modo) => void] {
  const mode = useSyncExternalStore(subscribe, read, () => "completo" as Modo);
  const setMode = useCallback((value: Modo) => {
    try {
      localStorage.setItem(KEY, value);
    } catch {
      // sin almacenamiento: el cambio dura solo esta visita
    }
    listeners.forEach((listener) => listener());
  }, []);
  return [mode, setMode];
}
