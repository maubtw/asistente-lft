"use client";

import { formatLongDate, type Meta, type Modo } from "@/lib/api";
import { HomeHeader, type SettingsProps } from "./Header";
import { SealLogo } from "./icons";
import { QuestionForm } from "./QuestionForm";
import { SuggestedTopics } from "./SuggestedTopics";

type Props = SettingsProps & {
  meta: Meta | null;
  mode: Modo;
  onModeChange: (mode: Modo) => void;
  onAsk: (question: string) => void;
};

/** Pantalla de inicio (docs/design/referencia/Main.dc.html), con la marca al centro. */
export function Home({ meta, mode, onModeChange, onAsk, ...settings }: Props) {
  const fecha = formatLongDate(meta?.fecha_reforma);
  return (
    <div className="flex min-h-screen flex-col bg-papel text-tinta">
      <HomeHeader {...settings} />

      <main className="flex flex-1 flex-col items-center justify-center px-6 pb-20">
        <div className="flex w-full max-w-[680px] flex-col items-center gap-9">
          <div className="flex flex-col items-center gap-5">
            <span className="flex items-center gap-3">
              <SealLogo size={40} />
              <span className="font-serif text-[24px] font-medium">Asistente LFT</span>
            </span>
            <h1 className="m-0 text-center font-serif text-[48px] leading-[1.08] font-medium tracking-[-0.02em]">
              ¿Qué dice la ley sobre tu trabajo?
            </h1>
          </div>
          <div className="flex w-full flex-col gap-4">
            <QuestionForm onAsk={onAsk} mode={mode} onModeChange={onModeChange} />
            <SuggestedTopics onAsk={onAsk} />
            {!settings.apiKey && (
              <p className="m-0 text-center text-[13px] text-grafito-claro">
                Para preguntar necesitas tu clave de API de OpenAI.{" "}
                <button
                  type="button"
                  onClick={() => settings.onSettingsOpenChange(true)}
                  className="cursor-pointer border-0 bg-transparent p-0 font-semibold text-sello underline underline-offset-[3px] hover:text-sello-oscuro"
                >
                  Agregar clave
                </button>
              </p>
            )}
          </div>
        </div>
      </main>

      <footer className="px-8 pt-[18px] pb-[22px] text-center text-[13px] leading-normal text-grafito-claro">
        Responde con base en la LFT vigente
        {fecha ? ` (última reforma en el DOF: ${fecha})` : ""}. Información orientativa; no
        sustituye asesoría legal.
      </footer>
    </div>
  );
}
