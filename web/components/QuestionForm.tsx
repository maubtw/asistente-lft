"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import type { Modo } from "@/lib/api";
import { ArrowUpIcon } from "./icons";
import { ModeSelect } from "./ModeSelect";

type Props = {
  onAsk: (question: string) => void;
  mode: Modo;
  onModeChange: (mode: Modo) => void;
  disabled?: boolean;
};

/** Campo de pregunta del inicio. Enter envía; Shift+Enter hace salto de línea. */
export function QuestionForm({ onAsk, mode, onModeChange, disabled = false }: Props) {
  const [question, setQuestion] = useState("");

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = question.trim();
    if (!text || disabled) return;
    onAsk(text);
    setQuestion("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      submit(event);
    }
  }

  return (
    <form onSubmit={submit} className="w-full">
      <label htmlFor="pregunta" className="sr-only">
        Tu pregunta sobre la Ley Federal del Trabajo
      </label>
      <div className="flex flex-col gap-3 rounded-[18px] border border-borde-campo bg-hoja pt-[18px] pr-3.5 pb-3.5 pl-5 shadow-campo has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-offset-2 has-[textarea:focus-visible]:outline-sello">
        <textarea
          id="pregunta"
          rows={2}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Pregunta con tus palabras, por ejemplo: ¿cuándo me tienen que pagar el aguinaldo?"
          className="w-full resize-none border-0 bg-transparent text-[17px] leading-normal text-tinta outline-none placeholder:text-grafito-claro"
        />
        <div className="flex items-center justify-between gap-3">
          <ModeSelect mode={mode} onChange={onModeChange} />
          <button
            type="submit"
            aria-label="Preguntar"
            disabled={disabled}
            className="flex size-11 cursor-pointer items-center justify-center rounded-xl bg-sello text-white hover:bg-sello-oscuro disabled:cursor-not-allowed"
          >
            <ArrowUpIcon />
          </button>
        </div>
      </div>
    </form>
  );
}
