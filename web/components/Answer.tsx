"use client";

import { useState } from "react";
import type { Selection, Turn } from "@/lib/conversation";
import { answerAsText, citedArticles } from "@/lib/conversation";
import { CitationChip } from "./CitationChip";
import { CopyIcon } from "./icons";
import { NoAnswerCard } from "./states";

type Props = {
  turn: Turn;
  selection: Selection | null;
  onSelectCitation: (turnId: number, articulo: string, pasaje: string | null) => void;
  onAsk: (question: string) => void;
};

const SERIF_BODY = "m-0 font-serif text-[19px] leading-[1.7] text-tinta-ley";

/** Respuesta: frase directa en serif grande y párrafos terminados en sus chips de cita. */
export function Answer({ turn, selection, onSelectCitation, onAsk }: Props) {
  const [copied, setCopied] = useState(false);
  const ready = turn.estado === "listo";
  const count = citedArticles(turn).length;

  if (turn.respuesta?.estado === "sin_respuesta") {
    return (
      <NoAnswerCard
        explanation={turn.respuesta.frase_principal}
        suggestion={turn.respuesta.sugerencia}
        onAsk={onAsk}
      />
    );
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(answerAsText(turn));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className="flex flex-col gap-[18px]" aria-busy={!ready}>
      {!ready && (
        <p className="sr-only" aria-live="polite">
          {turn.etapa ?? "Buscando en la ley…"}
        </p>
      )}
      {turn.frase && (
        <p className="m-0 font-serif text-[30px] leading-[1.2] font-medium tracking-[-0.015em]">
          {turn.frase}
        </p>
      )}
      {turn.parrafos.map((parrafo, index) => (
        <p key={index} className={SERIF_BODY}>
          {parrafo.texto}{" "}
          {parrafo.citas.map((cita) => (
            <CitationChip
              key={cita.articulo}
              articulo={cita.articulo}
              disabled={!ready}
              pressed={selection?.turnId === turn.id && selection.articulo === cita.articulo}
              onSelect={() => onSelectCitation(turn.id, cita.articulo, cita.pasaje)}
            />
          ))}
        </p>
      ))}

      {ready && (
        <div className="mt-1 flex flex-wrap items-center gap-2 border-t border-linea pt-4">
          <button
            type="button"
            onClick={copy}
            className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-[10px] px-3 text-[14px] font-medium text-tinta hover:bg-burbuja"
          >
            <CopyIcon />
            {copied ? "Copiada" : "Copiar respuesta"}
          </button>
          <span className="ml-auto text-[13px] text-grafito-claro">
            {count === 1 ? "1 artículo citado" : `${count} artículos citados`}
          </span>
        </div>
      )}
    </article>
  );
}
