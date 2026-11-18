/** Estado de la conversación: un turno por pregunta. */
import type { ApiError, Modo, Parrafo, Respuesta } from "./api";

export type Turn = {
  id: number;
  pregunta: string;
  modo: Modo;
  estado: "cargando" | "listo" | "error";
  etapa: string | null; // mensaje de la etapa en curso
  recuperados: string[]; // artículos encontrados mientras carga (pestañas provisionales)
  frase: string | null;
  parrafos: Parrafo[];
  respuesta: Respuesta | null;
  error: ApiError | null;
};

/** Qué muestra el panel de la ley: un artículo y los pasajes a resaltar. */
export type Selection = {
  turnId: number;
  articulo: string;
  pasajes: (string | null)[];
};

export function newTurn(id: number, pregunta: string, modo: Modo): Turn {
  return {
    id,
    pregunta,
    modo,
    estado: "cargando",
    etapa: null,
    recuperados: [],
    frase: null,
    parrafos: [],
    respuesta: null,
    error: null,
  };
}

/** Artículos citados en orden de aparición. */
export function citedArticles(turn: Turn): string[] {
  const ids = turn.parrafos.flatMap((p) => p.citas.map((c) => c.articulo));
  return [...new Set(ids)];
}

/** Todos los pasajes de un artículo en la respuesta (al elegir su pestaña). */
export function passagesFor(turn: Turn, articulo: string): (string | null)[] {
  return turn.parrafos.flatMap((p) => p.citas.filter((c) => c.articulo === articulo).map((c) => c.pasaje));
}

/** Texto para "Copiar respuesta": la respuesta con sus citas y la fuente. */
export function answerAsText(turn: Turn): string {
  const lines = [turn.frase ?? ""];
  for (const parrafo of turn.parrafos) {
    const cites = parrafo.citas.map((c) => `(Art. ${c.articulo}, LFT)`).join(" ");
    lines.push(`${parrafo.texto} ${cites}`);
  }
  const fecha = turn.respuesta?.fecha_reforma;
  lines.push(
    `Fuente: Ley Federal del Trabajo${fecha ? `, última reforma DOF ${fecha}` : ""}. ` +
      "Información orientativa; no sustituye asesoría legal.",
  );
  return lines.join("\n\n");
}
