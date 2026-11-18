import { MODE_HINTS, MODE_LABELS, type Modo } from "@/lib/api";

type Props = { mode: Modo; onChange: (mode: Modo) => void };

/** Tipo de respuesta dentro del campo de pregunta: Detallada (completo) / Rápida (ligero). */
export function ModeSelect({ mode, onChange }: Props) {
  return (
    <div role="group" aria-label="Tipo de respuesta" className="flex gap-0.5 rounded-[10px] bg-burbuja/60 p-0.5">
      {(Object.keys(MODE_LABELS) as Modo[]).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={mode === option}
          title={MODE_HINTS[option]}
          onClick={() => onChange(option)}
          className={`h-8 cursor-pointer rounded-lg px-3 text-[13px] font-medium ${
            mode === option ? "bg-hoja text-tinta shadow-[0_1px_0_#CDD2CB]" : "text-grafito hover:text-tinta"
          }`}
        >
          {MODE_LABELS[option]}
        </button>
      ))}
    </div>
  );
}
