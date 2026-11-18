type Props = { articulo: string; pressed: boolean; disabled?: boolean; onSelect: () => void };

/** Chip de cita al final de cada párrafo: abre el artículo en el panel. */
export function CitationChip({ articulo, pressed, disabled = false, onSelect }: Props) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onSelect}
      className={`ml-1 inline-block cursor-pointer rounded-[7px] border-0 px-[9px] py-1.5 align-[2px] font-sans text-[13px] leading-none font-semibold disabled:cursor-default ${
        pressed ? "bg-sello text-white" : "bg-sello-claro text-sello hover:bg-[#d4cef0]"
      }`}
    >
      Art. {articulo}
    </button>
  );
}
