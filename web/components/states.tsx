"use client";

import type { ApiError } from "@/lib/api";
import { SearchIcon } from "./icons";

/** "Preguntar cómo se fija el salario mínimo" a partir de "¿Cómo se fija el salario mínimo?". */
export function suggestionLabel(question: string): string {
  const bare = question.trim().replace(/^¿\s*/, "").replace(/\s*\?$/, "");
  const interrogative = /^(cómo|cuándo|cuánto|cuánta|cuántos|cuántas|qué|quién|quiénes|dónde|cuál|cuáles|por qué|para qué|en qué|a qué|de qué)\b/i;
  if (interrogative.test(bare)) {
    return `Preguntar ${bare.charAt(0).toLowerCase()}${bare.slice(1)}`;
  }
  return `Preguntar: ${question.trim()}`;
}

type NoAnswerProps = { explanation: string; suggestion: string | null; onAsk: (q: string) => void };

/** Sin respuesta (abstención): nunca se presenta como error. */
export function NoAnswerCard({ explanation, suggestion, onAsk }: NoAnswerProps) {
  return (
    <article className="flex flex-col gap-3 rounded-2xl border border-dashed border-[#A9B0A7] px-6 py-[22px]">
      <h3 className="m-0 flex items-center gap-2.5 text-[16px] font-semibold">
        <SearchIcon />
        Esto no está en la ley
      </h3>
      <p className="m-0 font-serif text-[18px] leading-[1.65] text-tinta-ley">{explanation}</p>
      {suggestion && (
        <button
          type="button"
          onClick={() => onAsk(suggestion)}
          className="h-10 cursor-pointer self-start rounded-[10px] border border-linea bg-transparent px-3.5 text-[14px] font-medium text-tinta hover:bg-burbuja"
        >
          {suggestionLabel(suggestion)}
        </button>
      )}
    </article>
  );
}

/** Mensaje de error según lo que pasó y qué hacer. */
export function errorMessage(error: ApiError | null): string {
  switch (error?.codigo) {
    case 400:
      return "Falta tu clave de API de OpenAI. Agrégala en Ajustes e intenta de nuevo.";
    case 401:
      return "Tu clave de API no es válida. Revísala en Ajustes e intenta de nuevo.";
    case 429:
      return "OpenAI rechazó la consulta por límite de uso o saldo. Revisa tu clave en Ajustes o intenta más tarde.";
    default:
      return "No pudimos conectar con el servicio. Revisa tu clave en Ajustes o intenta de nuevo.";
  }
}

type ErrorProps = { error: ApiError | null; onRetry: () => void; onOpenSettings?: () => void };

const KEY_ERRORS = new Set([400, 401]);

export function ErrorCard({ error, onRetry, onOpenSettings }: ErrorProps) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-2xl border border-linea bg-hoja px-6 py-5">
      <p className="m-0 text-[16px] leading-normal text-tinta">{errorMessage(error)}</p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onRetry}
          className="h-10 cursor-pointer rounded-[10px] border border-linea bg-transparent px-3.5 text-[14px] font-medium text-tinta hover:bg-burbuja"
        >
          Reintentar
        </button>
        {onOpenSettings && error?.codigo != null && KEY_ERRORS.has(error.codigo) && (
          <button
            type="button"
            onClick={onOpenSettings}
            className="h-10 cursor-pointer rounded-[10px] border-0 bg-transparent px-3.5 text-[14px] font-semibold text-sello hover:bg-sello-claro"
          >
            Abrir ajustes
          </button>
        )}
      </div>
    </div>
  );
}
