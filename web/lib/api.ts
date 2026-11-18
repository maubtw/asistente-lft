/** Cliente de la API (FastAPI). Tipos del contrato de docs/design/DESIGN.md. */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Cita = { articulo: string; pasaje: string | null };
export type Parrafo = { texto: string; citas: Cita[] };
export type ArticuloCitado = {
  titulo: string | null;
  capitulo: string | null;
  texto: string;
  referencias: string[];
  texto_parcial?: boolean;
};
export type Respuesta = {
  estado: "respondida" | "sin_respuesta";
  frase_principal: string;
  parrafos: Parrafo[];
  sugerencia: string | null;
  articulos: Record<string, ArticuloCitado>;
  fecha_reforma: string | null;
};
export type Meta = { fecha_reforma: string | null; articulos_vigentes: number };

export async function getMeta(signal?: AbortSignal): Promise<Meta | null> {
  try {
    const response = await fetch(`${API_URL}/meta`, { signal });
    return response.ok ? ((await response.json()) as Meta) : null;
  } catch {
    return null;
  }
}

const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** "2026-05-14" → "14 de mayo de 2026" */
export function formatLongDate(iso: string | null | undefined): string | null {
  const match = iso?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const [, year, month, day] = match;
  return `${Number(day)} de ${MONTHS[Number(month) - 1]} de ${year}`;
}

// --- Preguntar (SSE) --------------------------------------------------------------------

export type Modo = "completo" | "ligero";
export const MODE_LABELS: Record<Modo, string> = { completo: "Detallada", ligero: "Rápida" };
export const MODE_HINTS: Record<Modo, string> = {
  completo: "Revisa más artículos y los reordena. Tarda ~20 s.",
  ligero: "Más rápida, con menos revisión. Tarda ~10 s.",
};

export type Etapa = { etapa: string; mensaje: string };
export type ParrafoEvento = Parrafo & { indice: number };

export type StreamHandlers = {
  onEtapa?: (etapa: Etapa) => void;
  onArticulos?: (ids: string[]) => void;
  onFrase?: (frase: string) => void;
  onParrafo?: (parrafo: ParrafoEvento) => void;
  onFin: (respuesta: Respuesta) => void;
  onError: (error: ApiError) => void;
};

export type ApiError = { codigo: number | null; mensaje: string };

/** POST /ask/stream con fetch + ReadableStream (EventSource no admite POST ni encabezados). */
export async function askStream(
  pregunta: string,
  modo: Modo,
  handlers: StreamHandlers,
  options: { apiKey?: string; signal?: AbortSignal } = {},
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/ask/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(options.apiKey ? { "X-OpenAI-Key": options.apiKey } : {}),
      },
      body: JSON.stringify({ pregunta, modo }),
      signal: options.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") return;
    handlers.onError({ codigo: null, mensaje: "No pudimos conectar con el servicio." });
    return;
  }
  if (!response.ok || !response.body) {
    const detail = await response.json().catch(() => null);
    handlers.onError({ codigo: response.status, mensaje: detail?.detail ?? "Error del servicio." });
    return;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let finished = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        finished = dispatch(block, handlers) || finished;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } catch (error) {
    if ((error as Error).name === "AbortError") return;
    handlers.onError({ codigo: null, mensaje: "Se interrumpió la conexión con el servicio." });
    return;
  }
  if (!finished) {
    handlers.onError({ codigo: null, mensaje: "La respuesta llegó incompleta." });
  }
}

/** Procesa un bloque SSE. Devuelve true si fue el evento final (fin o error). */
function dispatch(block: string, handlers: StreamHandlers): boolean {
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!data) return false;
  const payload = JSON.parse(data);
  switch (event) {
    case "etapa":
      handlers.onEtapa?.(payload as Etapa);
      return false;
    case "articulos":
      handlers.onArticulos?.(payload.ids as string[]);
      return false;
    case "frase":
      handlers.onFrase?.(payload.frase_principal as string);
      return false;
    case "parrafo":
      handlers.onParrafo?.(payload as ParrafoEvento);
      return false;
    case "fin":
      handlers.onFin(payload as Respuesta);
      return true;
    case "error":
      handlers.onError(payload as ApiError);
      return true;
    default:
      return false;
  }
}

/** GET /articulo/{id}: para "Este artículo remite al artículo X" cuando X no fue citado. */
export async function getArticulo(id: string): Promise<ArticuloCitado | null> {
  try {
    const response = await fetch(`${API_URL}/articulo/${encodeURIComponent(id)}`);
    if (!response.ok) return null;
    const data = await response.json();
    return {
      titulo: data.titulo,
      capitulo: data.capitulo,
      texto: data.texto,
      referencias: data.referencias ?? [],
    };
  } catch {
    return null;
  }
}

export type Health = {
  status: string;
  articulos_vigentes: number;
  fecha_reforma: string | null;
  requiere_clave_usuario: boolean;
};

export async function getHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return response.ok ? ((await response.json()) as Health) : null;
  } catch {
    return null;
  }
}
