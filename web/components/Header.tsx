import { PlusIcon, SealLogo } from "./icons";
import { SettingsMenu } from "./SettingsMenu";

export type SettingsProps = {
  settingsOpen: boolean;
  onSettingsOpenChange: (open: boolean) => void;
  apiKey: string;
  onApiKeyChange: (key: string) => void;
  pendingQuestion: string | null;
  onSubmitPending: () => void;
};

/** Inicio: la marca va al centro de la pantalla; aquí solo queda Ajustes. */
export function HomeHeader(props: SettingsProps) {
  return (
    <header className="flex items-center justify-end px-8 py-5">
      <SettingsMenu
        open={props.settingsOpen}
        onOpenChange={props.onSettingsOpenChange}
        apiKey={props.apiKey}
        onApiKeyChange={props.onApiKeyChange}
        pendingQuestion={props.pendingQuestion}
        onSubmitPending={props.onSubmitPending}
      />
    </header>
  );
}

/** Conversación (Respuesta.dc.html): logo a la izquierda, "Nueva consulta" y Ajustes. */
export function ConversationHeader({ onNewQuery, ...props }: SettingsProps & { onNewQuery: () => void }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-linea px-[clamp(20px,4vw,48px)] py-4">
      <button
        type="button"
        onClick={onNewQuery}
        className="flex cursor-pointer items-center gap-3 rounded-md text-tinta"
        aria-label="Asistente LFT: volver al inicio"
      >
        <SealLogo size={30} />
        <span className="font-serif text-[19px] font-medium">Asistente LFT</span>
      </button>
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          onClick={onNewQuery}
          className="inline-flex h-11 cursor-pointer items-center gap-2 rounded-xl border border-linea px-4 text-[14px] font-semibold text-tinta hover:bg-burbuja"
        >
          <PlusIcon />
          Nueva consulta
        </button>
        <SettingsMenu
          open={props.settingsOpen}
          onOpenChange={props.onSettingsOpenChange}
          apiKey={props.apiKey}
          onApiKeyChange={props.onApiKeyChange}
          pendingQuestion={props.pendingQuestion}
          onSubmitPending={props.onSubmitPending}
          bordered
        />
      </div>
    </header>
  );
}
