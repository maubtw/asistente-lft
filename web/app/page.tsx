"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Conversation } from "@/components/Conversation";
import { Home } from "@/components/Home";
import { askStream, getArticulo, getMeta, type ArticuloCitado, type Meta, type Modo } from "@/lib/api";
import { newTurn, type Selection, type Turn } from "@/lib/conversation";
import { useApiKey } from "@/lib/useApiKey";
import { useStoredMode } from "@/lib/useStoredMode";

export default function Page() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [mode, changeMode] = useStoredMode();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [extraArticles, setExtraArticles] = useState<Record<string, ArticuloCitado>>({});
  // Clave obligatoria del usuario (sessionStorage: se borra al cerrar la pestaña).
  const [apiKey, setApiKey] = useApiKey();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const nextId = useRef(1);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    getMeta(abort.signal).then(setMeta);
    return () => abort.abort();
  }, []);

  const update = useCallback((id: number, patch: (turn: Turn) => Partial<Turn>) => {
    setTurns((all) => all.map((turn) => (turn.id === id ? { ...turn, ...patch(turn) } : turn)));
  }, []);

  function ask(question: string) {
    if (!apiKey) {
      // Sin clave no se pregunta: se abre Ajustes y la pregunta espera.
      setPendingQuestion(question);
      setSettingsOpen(true);
      return;
    }
    send(question);
  }

  function submitPending() {
    const question = pendingQuestion;
    setPendingQuestion(null);
    setSettingsOpen(false);
    if (question && apiKey) send(question);
  }

  function changeSettingsOpen(open: boolean) {
    setSettingsOpen(open);
    if (!open) setPendingQuestion(null);
  }

  function send(question: string) {
    const id = nextId.current++;
    setTurns((all) => [...all, newTurn(id, question, mode)]);
    run(id, question, mode);
  }

  /** "Reintentar": repite la misma pregunta en el mismo turno. */
  function retry(turnId: number) {
    const turn = turns.find((t) => t.id === turnId);
    if (!turn) return;
    update(turnId, () => newTurn(turnId, turn.pregunta, turn.modo));
    run(turnId, turn.pregunta, turn.modo);
  }

  function run(id: number, question: string, turnMode: Modo) {
    setSelection(null);
    controller.current?.abort();
    controller.current = new AbortController();

    askStream(
      question,
      turnMode,
      {
        onEtapa: ({ mensaje }) => update(id, () => ({ etapa: mensaje })),
        onArticulos: (ids) => update(id, () => ({ recuperados: ids })),
        onFrase: (frase) => update(id, () => ({ frase })),
        onParrafo: ({ texto, citas, indice }) =>
          update(id, (turn) => {
            const parrafos = [...turn.parrafos];
            parrafos[indice] = { texto, citas };
            return { parrafos };
          }),
        onFin: (respuesta) => {
          update(id, () => ({
            estado: "listo",
            etapa: null,
            respuesta,
            frase: respuesta.frase_principal,
            parrafos: respuesta.parrafos, // el contrato final manda
          }));
          const first = respuesta.parrafos[0]?.citas[0];
          if (first) setSelection({ turnId: id, articulo: first.articulo, pasajes: [first.pasaje] });
        },
        onError: (error) => update(id, () => ({ estado: "error", etapa: null, error })),
      },
      { signal: controller.current.signal, apiKey },
    );
  }

  function newQuery() {
    controller.current?.abort();
    setTurns([]);
    setSelection(null);
  }

  async function openReference(turnId: number, articulo: string) {
    const turn = turns.find((t) => t.id === turnId);
    const passages = turn?.parrafos.flatMap((p) => p.citas.filter((c) => c.articulo === articulo).map((c) => c.pasaje)) ?? [];
    if (!turn?.respuesta?.articulos[articulo] && !extraArticles[articulo]) {
      const fetched = await getArticulo(articulo);
      if (!fetched) return;
      setExtraArticles((all) => ({ ...all, [articulo]: fetched }));
    }
    setSelection({ turnId, articulo, pasajes: passages });
  }

  if (turns.length === 0) {
    return (
      <Home
        meta={meta}
        mode={mode}
        onModeChange={changeMode}
        onAsk={ask}
        settingsOpen={settingsOpen}
        onSettingsOpenChange={changeSettingsOpen}
        apiKey={apiKey}
        onApiKeyChange={setApiKey}
        pendingQuestion={pendingQuestion}
        onSubmitPending={submitPending}
      />
    );
  }
  return (
    <Conversation
      turns={turns}
      selection={selection}
      extraArticles={extraArticles}
      mode={mode}
      onModeChange={changeMode}
      onAsk={ask}
      onNewQuery={newQuery}
      onSelect={(turnId, articulo, pasajes) => setSelection({ turnId, articulo, pasajes })}
      onOpenReference={openReference}
      onRetry={retry}
      settingsOpen={settingsOpen}
      onSettingsOpenChange={changeSettingsOpen}
      apiKey={apiKey}
      onApiKeyChange={setApiKey}
      pendingQuestion={pendingQuestion}
      onSubmitPending={submitPending}
    />
  );
}
