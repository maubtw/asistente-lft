"use client";

import { useCallback, useSyncExternalStore } from "react";

/** Clave de API del usuario, en sessionStorage: sobrevive a recargar la página pero se borra al
 * cerrar la pestaña. Nunca va a disco del servidor ni a localStorage. Si el almacenamiento no
 * está disponible (modo privado estricto), vive solo en memoria. */
const KEY = "asistente-lft:clave";
const listeners = new Set<() => void>();
let memory = "";

function read(): string {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return memory;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useApiKey(): [string, (key: string) => void] {
  const apiKey = useSyncExternalStore(subscribe, read, () => "");
  const setApiKey = useCallback((value: string) => {
    memory = value;
    try {
      if (value) sessionStorage.setItem(KEY, value);
      else sessionStorage.removeItem(KEY);
    } catch {
      // sin sessionStorage: queda en memoria
    }
    listeners.forEach((listener) => listener());
  }, []);
  return [apiKey, setApiKey];
}
