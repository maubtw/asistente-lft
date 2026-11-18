/** Temas sugeridos: al hacer clic se envía una pregunta completa sobre ese tema. */
export const TOPICS = [
  { label: "Días de vacaciones", question: "Llevo 3 años en la empresa, ¿cuántos días de vacaciones me tocan?" },
  { label: "Despido sin causa", question: "Me despidieron sin causa, ¿qué puedo exigir?" },
  { label: "Horas extra", question: "¿Cuánto me deben pagar por las horas extra?" },
  { label: "Permiso de paternidad", question: "¿Los papás tienen derecho a permiso cuando nace su hijo?" },
] as const;

type Props = { onAsk: (question: string) => void; disabled?: boolean };

export function SuggestedTopics({ onAsk, disabled = false }: Props) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {TOPICS.map((topic) => (
        <button
          key={topic.label}
          type="button"
          disabled={disabled}
          onClick={() => onAsk(topic.question)}
          className="h-9 cursor-pointer rounded-[18px] border border-linea bg-transparent px-3.5 text-[14px] text-grafito hover:bg-burbuja hover:text-tinta"
        >
          {topic.label}
        </button>
      ))}
    </div>
  );
}
