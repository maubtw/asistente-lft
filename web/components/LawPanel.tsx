"use client";

import { useEffect, useRef } from "react";
import { formatLongDate, type ArticuloCitado } from "@/lib/api";
import { highlightSegments, referencePhrase } from "@/lib/highlight";

const LFT_PDF = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf";

type Props = {
  tabs: string[]; // artículos citados de la respuesta activa
  activeId: string | null;
  article: ArticuloCitado | null;
  passages: (string | null)[];
  fechaReforma: string | null;
  loadingMessage: string | null; // mientras se recupera: "Buscando en la ley…"
  emptyMessage?: string | null; // sin respuesta o error: no hay artículo que mostrar
  onSelectTab: (articulo: string) => void;
  onOpenReference: (articulo: string) => void;
};

/** Panel de la ley: la hoja con el artículo y el pasaje que sustenta la respuesta resaltado. */
export function LawPanel({
  tabs,
  activeId,
  article,
  passages,
  fechaReforma,
  loadingMessage,
  emptyMessage = null,
  onSelectTab,
  onOpenReference,
}: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLElement>(null);
  const segments = article ? highlightSegments(article.texto, passages) : [];
  const hasMark = segments.some((s) => s.marked);
  const selectionKey = `${activeId}|${passages.join("|")}`;

  // Lleva el pasaje resaltado a la vista dentro del panel (sin mover la página).
  useEffect(() => {
    const body = bodyRef.current;
    const mark = markRef.current;
    if (!body) return;
    body.scrollTop = mark ? Math.max(0, mark.offsetTop - body.clientHeight / 3) : 0;
  }, [selectionKey]);

  const crumb = [article?.titulo, article?.capitulo].filter(Boolean).join(" › ");
  const fecha = formatLongDate(fechaReforma);
  const firstMarked = segments.findIndex((s) => s.marked);

  return (
    <aside aria-label="Texto de la ley" className="sticky top-6 min-w-0 flex-[1_1_440px]">
      <div className="flex max-h-[calc(100vh-48px)] flex-col overflow-hidden rounded-md bg-hoja shadow-[0_1px_0_#CDD2CB,0_30px_60px_-30px_rgba(24,32,43,0.28)]">
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-[#DEE2DB] px-5 py-4">
          <h2 className="m-0 text-[14px] font-semibold">Artículos citados</h2>
          <div role="group" aria-label="Elegir artículo" className="flex gap-1">
            {tabs.map((id) => (
              <button
                key={id}
                type="button"
                aria-pressed={id === activeId}
                disabled={!!loadingMessage}
                onClick={() => onSelectTab(id)}
                className={`h-9 min-w-11 cursor-pointer rounded-[9px] px-2 text-[14px] font-semibold disabled:cursor-default ${
                  id === activeId ? "bg-sello text-white" : "bg-transparent text-sello hover:bg-sello-claro"
                }`}
              >
                {id}
              </button>
            ))}
          </div>
        </div>

        <div ref={bodyRef} className="relative flex flex-col gap-3.5 overflow-y-auto px-9 pt-8 pb-9">
          {loadingMessage || !article ? (
            <p className="m-0 font-serif text-[18px] leading-[1.72] text-grafito" aria-live="polite">
              {loadingMessage ?? emptyMessage ?? "Elige una cita para ver el artículo."}
            </p>
          ) : (
            <>
              {crumb && <p className="m-0 text-[13px] text-grafito-claro">{crumb}</p>}
              <h3 aria-live="polite" className="m-0 font-serif text-[32px] font-medium tracking-[-0.015em]">
                Artículo {activeId}
              </h3>
              <p className="m-0 font-serif text-[18px] leading-[1.72] whitespace-pre-line text-tinta-ley">
                {segments.map((segment, index) => {
                  if (!segment.marked) return <span key={index}>{segment.text}</span>;
                  return (
                    <mark
                      key={`${selectionKey}-${index}`}
                      ref={index === firstMarked ? markRef : undefined}
                      className="highlight"
                    >
                      {segment.text}
                    </mark>
                  );
                })}
              </p>
              {article.texto_parcial && (
                <p className="m-0 text-[13.5px] leading-normal text-grafito">
                  Este artículo es muy extenso: se muestra solo la parte que se usó para responder.
                </p>
              )}
              {hasMark && (
                <p className="mt-1 mb-0 flex items-center gap-2 text-[13.5px] leading-normal text-grafito">
                  <span aria-hidden="true" className="inline-block h-2.5 w-[22px] rounded-[2px] bg-resaltador" />
                  Lo marcado es lo que usamos para responder.
                </p>
              )}
              {article.referencias.length > 0 && (
                <p className="m-0 text-[13.5px] text-grafito">
                  {referencePhrase(article.referencias).prefix}{" "}
                  {article.referencias.map((ref, index) => (
                    <span key={ref}>
                      {index > 0 && (index === article.referencias.length - 1 ? " y " : ", ")}
                      <button
                        type="button"
                        onClick={() => onOpenReference(ref)}
                        className="cursor-pointer border-0 bg-transparent p-0 font-semibold text-sello underline underline-offset-[3px] hover:text-sello-oscuro"
                      >
                        {ref}
                      </button>
                    </span>
                  ))}
                  .
                </p>
              )}
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2.5 bg-hoja-pie px-5 py-3.5 text-[13px] text-grafito-claro">
          <span>{fecha ? `Texto vigente al ${fecha}` : "Texto vigente de la LFT"}</span>
          <a href={LFT_PDF} target="_blank" rel="noopener noreferrer" className="font-semibold text-sello hover:text-sello-oscuro">
            Leer la ley completa
          </a>
        </div>
      </div>
    </aside>
  );
}
