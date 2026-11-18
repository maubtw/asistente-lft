"use client";

import { useEffect, useId, useRef, useState } from "react";
import { API_URL, formatLongDate, getHealth, type Health } from "@/lib/api";
import { SettingsIcon } from "./icons";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apiKey: string;
  onApiKeyChange: (key: string) => void;
  /** Pregunta que espera a que el usuario ponga su clave ("Guardar y preguntar"). */
  pendingQuestion?: string | null;
  onSubmitPending?: () => void;
  bordered?: boolean;
};

type Connection = { state: "comprobando" } | { state: "ok"; health: Health } | { state: "sin_conexion" };

/** Ajustes (popover desde el ícono): clave de API y estado de la conexión. */
export function SettingsMenu({
  open,
  onOpenChange,
  apiKey,
  onApiKeyChange,
  pendingQuestion = null,
  onSubmitPending,
  bordered = false,
}: Props) {
  const [connection, setConnection] = useState<Connection>({ state: "comprobando" });
  const [showKey, setShowKey] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelId = useId();

  async function check() {
    setConnection({ state: "comprobando" });
    const health = await getHealth();
    setConnection(health ? { state: "ok", health } : { state: "sin_conexion" });
  }

  // Al abrir: comprobar la conexión y llevar el foco al campo de la clave.
  useEffect(() => {
    if (!open) return;
    let active = true;
    getHealth().then((health) => {
      if (active) setConnection(health ? { state: "ok", health } : { state: "sin_conexion" });
    });
    inputRef.current?.focus();
    return () => {
      active = false;
    };
  }, [open]);

  // Cerrar con Escape o clic fuera; el foco regresa al botón de Ajustes.
  useEffect(() => {
    if (!open) return;
    const close = () => {
      onOpenChange(false);
      buttonRef.current?.focus();
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onOpenChange(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, onOpenChange]);

  const fecha = connection.state === "ok" ? formatLongDate(connection.health.fecha_reforma) : null;

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label="Ajustes"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => onOpenChange(!open)}
        className={`flex size-11 cursor-pointer items-center justify-center rounded-xl hover:bg-burbuja ${
          bordered ? "border border-linea text-tinta" : "text-grafito hover:text-tinta"
        } ${open ? "bg-burbuja text-tinta" : ""}`}
      >
        <SettingsIcon />
      </button>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="Ajustes"
          className="absolute top-[52px] right-0 z-20 flex w-[360px] flex-col gap-5 rounded-xl border border-linea bg-hoja p-5 text-left shadow-[0_1px_0_#CDD2CB,0_30px_60px_-30px_rgba(24,32,43,0.28)]"
        >
          <h2 className="m-0 text-[15px] font-semibold">Ajustes</h2>

          {!apiKey && (
            <p className="m-0 rounded-[10px] bg-sello-claro px-3.5 py-3 text-[14px] leading-normal text-tinta">
              Para preguntar necesitas tu propia clave de API de OpenAI.
            </p>
          )}

          <form
            className="flex flex-col gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!apiKey) return;
              if (pendingQuestion && onSubmitPending) onSubmitPending();
              else onOpenChange(false);
            }}
          >
            <label htmlFor={`${panelId}-key`} className="text-[14px] font-medium">
              Clave de API de OpenAI
            </label>
            <div className="flex items-center gap-2 rounded-[10px] border border-borde-campo bg-papel/40 pr-1.5 pl-3 has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-sello">
              <input
                ref={inputRef}
                id={`${panelId}-key`}
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(event) => onApiKeyChange(event.target.value.trim())}
                placeholder="sk-…"
                autoComplete="off"
                spellCheck={false}
                required
                aria-describedby={`${panelId}-key-help`}
                className="h-10 min-w-0 flex-1 border-0 bg-transparent text-[14px] text-tinta outline-none placeholder:text-grafito-claro"
              />
              <button
                type="button"
                onClick={() => setShowKey((value) => !value)}
                className="h-8 cursor-pointer rounded-lg px-2 text-[13px] font-medium text-grafito hover:bg-burbuja hover:text-tinta"
              >
                {showKey ? "Ocultar" : "Mostrar"}
              </button>
            </div>
            <p id={`${panelId}-key-help`} className="m-0 text-[13px] leading-normal text-grafito-claro">
              Se envía solo a tu API local, que la usa para consultar a OpenAI; nunca se guarda en el
              servidor. En el navegador se borra al cerrar esta pestaña. Puedes crear una en{" "}
              <a
                href="https://platform.openai.com/api-keys"
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-sello hover:text-sello-oscuro"
              >
                platform.openai.com
              </a>
              .
            </p>
            <div className="mt-1 flex items-center gap-3">
              <button
                type="submit"
                disabled={!apiKey}
                className="h-10 cursor-pointer rounded-[10px] bg-sello px-4 text-[14px] font-semibold text-white hover:bg-sello-oscuro disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pendingQuestion ? "Guardar y preguntar" : "Guardar"}
              </button>
              {apiKey && (
                <button
                  type="button"
                  onClick={() => onApiKeyChange("")}
                  className="cursor-pointer border-0 bg-transparent p-0 text-[13px] font-semibold text-sello underline underline-offset-[3px] hover:text-sello-oscuro"
                >
                  Quitar clave
                </button>
              )}
            </div>
          </form>

          <div className="flex flex-col gap-2 border-t border-linea pt-4">
            <h3 className="m-0 text-[14px] font-medium">Estado de la conexión</h3>
            <p className="m-0 flex items-center gap-2 text-[14px]" aria-live="polite">
              <span
                aria-hidden="true"
                className={`inline-block size-2 rounded-full ${
                  connection.state === "ok"
                    ? "bg-sello"
                    : connection.state === "sin_conexion"
                      ? "border-[1.5px] border-grafito"
                      : "bg-linea"
                }`}
              />
              {connection.state === "ok"
                ? "Conectado a la API"
                : connection.state === "sin_conexion"
                  ? "Sin conexión con la API"
                  : "Comprobando…"}
            </p>
            {connection.state === "ok" && (
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[13px] leading-normal text-grafito">
                <li>
                  Ley vigente al {fecha ?? "—"} · {connection.health.articulos_vigentes.toLocaleString("es-MX")} artículos
                </li>
                <li>{apiKey ? "Clave lista para esta pestaña." : "Falta tu clave de API."}</li>
              </ul>
            )}
            {connection.state === "sin_conexion" && (
              <p className="m-0 text-[13px] leading-normal text-grafito">
                No responde {API_URL}. Arráncala con <code className="font-sans">make api</code>.
              </p>
            )}
            <button
              type="button"
              onClick={check}
              className="h-9 cursor-pointer self-start rounded-[10px] border border-linea bg-transparent px-3 text-[13px] font-medium text-tinta hover:bg-burbuja"
            >
              Comprobar de nuevo
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
