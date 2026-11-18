"use client";

import { useEffect, useRef } from "react";

const NEAR_BOTTOM_PX = 160;

function atBottom(): boolean {
  return window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - NEAR_BOTTOM_PX;
}

function scrollToBottom() {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior: reduce ? "auto" : "smooth" });
}

/** Mantiene a la vista el final de la conversación.
 *
 * - Pregunta nueva (`count` cambia): siempre baja.
 * - Contenido que llega por streaming (`signature` cambia): baja solo si el usuario ya estaba
 *   abajo; si subió a leer, no lo mueve.
 */
export function useFollowBottom(count: number, signature: string) {
  const stick = useRef(true);
  const previousCount = useRef(count);

  useEffect(() => {
    const onScroll = () => {
      stick.current = atBottom();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const newTurn = count > previousCount.current;
    previousCount.current = count;
    if (newTurn || stick.current) {
      stick.current = true;
      scrollToBottom();
    }
  }, [count, signature]);
}
