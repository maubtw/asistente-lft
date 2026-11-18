"use client";

import { useState, type FormEvent } from "react";
import type { Modo } from "@/lib/api";
import { ModeSelect } from "./ModeSelect";

type Props = {
  onAsk: (question: string) => void;
  mode: Modo;
  onModeChange: (mode: Modo) => void;
  disabled?: boolean;
};

/** Campo fijo abajo para seguir preguntando (Respuesta.dc.html). */
export function FollowUpForm({ onAsk, mode, onModeChange, disabled = false }: Props) {
  const [question, setQuestion] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || disabled) return;
    onAsk(text);
    setQuestion("");
  }

  return (
    <form
      onSubmit={submit}
      className="sticky bottom-5 flex items-center gap-2.5 rounded-2xl border border-borde-campo bg-hoja py-2 pr-2 pl-[18px] shadow-[0_18px_40px_-24px_rgba(24,32,43,0.35)] has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-sello"
    >
      <label htmlFor="otra" className="sr-only">
        Haz otra pregunta
      </label>
      <input
        id="otra"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder="Haz otra pregunta sobre la LFT"
        autoComplete="off"
        className="h-11 min-w-0 flex-1 border-0 bg-transparent text-[16px] text-tinta outline-none placeholder:text-grafito-claro"
      />
      <ModeSelect mode={mode} onChange={onModeChange} />
      <button
        type="submit"
        disabled={disabled}
        className="h-11 cursor-pointer rounded-[11px] bg-sello px-[18px] text-[15px] font-semibold text-white hover:bg-sello-oscuro disabled:cursor-not-allowed disabled:opacity-60"
      >
        Preguntar
      </button>
    </form>
  );
}
