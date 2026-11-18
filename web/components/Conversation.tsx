"use client";

import type { ArticuloCitado, Modo } from "@/lib/api";
import { citedArticles, type Selection, type Turn } from "@/lib/conversation";
import { Answer } from "./Answer";
import { FollowUpForm } from "./FollowUpForm";
import { ConversationHeader, type SettingsProps } from "./Header";
import { LawPanel } from "./LawPanel";
import { ErrorCard } from "./states";
import { useFollowBottom } from "@/lib/useFollowBottom";

type Props = SettingsProps & {
  turns: Turn[];
  selection: Selection | null;
  extraArticles: Record<string, ArticuloCitado>;
  mode: Modo;
  onModeChange: (mode: Modo) => void;
  onAsk: (question: string) => void;
  onNewQuery: () => void;
  onSelect: (turnId: number, articulo: string, pasajes: (string | null)[]) => void;
  onOpenReference: (turnId: number, articulo: string) => void;
  onRetry: (turnId: number) => void;
};

/** Conversación a la izquierda; panel de la ley a la derecha. */
export function Conversation(props: Props) {
  const { turns, selection, extraArticles, mode, onModeChange, onAsk, onNewQuery, onSelect } = props;
  const loading = turns.some((t) => t.estado === "cargando");
  const last = turns.at(-1)!;
  useFollowBottom(
    turns.length,
    `${last.estado}|${last.frase ?? ""}|${last.parrafos.length}|${last.respuesta ? 1 : 0}`,
  );
  const panelTurn = turns.find((t) => t.id === selection?.turnId) ?? last;
  const tabs = panelTurn.estado === "cargando" ? panelTurn.recuperados : citedArticles(panelTurn);
  const activeId = selection?.turnId === panelTurn.id ? selection.articulo : null;
  const article = activeId
    ? (panelTurn.respuesta?.articulos[activeId] ?? extraArticles[activeId] ?? null)
    : null;

  return (
    <div className="min-h-screen bg-papel text-tinta">
      <ConversationHeader
        onNewQuery={onNewQuery}
        settingsOpen={props.settingsOpen}
        onSettingsOpenChange={props.onSettingsOpenChange}
        apiKey={props.apiKey}
        onApiKeyChange={props.onApiKeyChange}
        pendingQuestion={props.pendingQuestion}
        onSubmitPending={props.onSubmitPending}
      />
      <div className="mx-auto flex max-w-[1320px] items-start gap-14 px-[clamp(20px,4vw,48px)] pt-10 pb-12">
        <section aria-label="Conversación" className="flex max-w-[720px] min-w-0 flex-[999_1_560px] flex-col gap-8">
          {turns.map((turn) => (
            <div key={turn.id} className="flex flex-col gap-8">
              <div className="max-w-[85%] self-end rounded-[16px_16px_4px_16px] bg-burbuja px-[18px] py-3.5 text-[17px] leading-[1.45]">
                {turn.pregunta}
              </div>
              {turn.estado === "error" ? (
                <ErrorCard
                  error={turn.error}
                  onRetry={() => props.onRetry(turn.id)}
                  onOpenSettings={() => props.onSettingsOpenChange(true)}
                />
              ) : (
                <Answer
                  turn={turn}
                  selection={selection}
                  onAsk={onAsk}
                  onSelectCitation={(turnId, articulo, pasaje) => onSelect(turnId, articulo, [pasaje])}
                />
              )}
            </div>
          ))}
          <FollowUpForm onAsk={onAsk} mode={mode} onModeChange={onModeChange} disabled={loading} />
        </section>

        <LawPanel
          tabs={tabs}
          activeId={activeId}
          article={article}
          passages={selection?.turnId === panelTurn.id ? selection.pasajes : []}
          fechaReforma={panelTurn.respuesta?.fecha_reforma ?? null}
          loadingMessage={panelTurn.estado === "cargando" ? (panelTurn.etapa ?? "Buscando en la ley…") : null}
          emptyMessage={
            panelTurn.estado === "error"
              ? "No hay artículos que mostrar para esta consulta."
              : panelTurn.respuesta?.estado === "sin_respuesta"
                ? "Ningún artículo de la LFT responde esta pregunta."
                : null
          }
          onSelectTab={(articulo) => {
            const passages = panelTurn.parrafos.flatMap((p) =>
              p.citas.filter((c) => c.articulo === articulo).map((c) => c.pasaje),
            );
            onSelect(panelTurn.id, articulo, passages);
          }}
          onOpenReference={(articulo) => props.onOpenReference(panelTurn.id, articulo)}
        />
      </div>
    </div>
  );
}
