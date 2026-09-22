/**
 * realtime — WebSocket do app do entregador (canal `driver:{driver_id}`).
 *
 * Ponto crítico do gate: o backend fecha com **4003 "Password change
 * required"** quando a troca de senha está pendente. Esse fechamento NÃO é
 * "erro de rede" — é estado de app: chama `onPasswordChangeRequired` e para de
 * reconectar (não faz sentido insistir até o usuário trocar a senha).
 *
 * WebSocket injetável → testável em node --test com um fake, sem RN.
 * Módulo puro.
 */

export interface RealtimeDeps {
  /**
   * WebSocket já construído pelo chamador (ex.: `new WebSocket(url)`).
   * Handlers como `unknown` para aceitar tanto o WebSocket do RN/DOM quanto
   * um fake nos testes, sem briga de variância de tipo.
   */
  socket: {
    close(): void;
    onopen: unknown;
    onmessage: unknown;
    onclose: unknown;
    onerror: unknown;
  };
  onEvent?: (data: unknown) => void;
  onOpen?: () => void;
  onClose?: (code: number) => void;
  onPasswordChangeRequired?: () => void;
  log?: (message: string) => void;
}

const WS_PASSWORD_CHANGE_REQUIRED = 4003;

/**
 * Liga os handlers e devolve um controlador. Um `close()` remoto com 4003
 * sinaliza o gate; qualquer outro fechamento é reportado ao chamador, que
 * decide reconectar.
 */
export function attachDriverSocket({ socket, onEvent, onOpen, onClose, onPasswordChangeRequired, log }: RealtimeDeps): {
  close(): void;
  stoppedByPasswordGate(): boolean;
} {
  let passwordGate = false;

  socket.onopen = () => {
    log?.("ws.open");
    onOpen?.();
  };

  socket.onmessage = (ev: { data: unknown }) => {
    let parsed: unknown = ev.data;
    if (typeof ev.data === "string") {
      try {
        parsed = JSON.parse(ev.data);
      } catch {
        /* texto cru — passa adiante mesmo assim */
      }
    }
    onEvent?.(parsed);
  };

  socket.onerror = () => {
    log?.("ws.error");
  };

  socket.onclose = (ev: { code: number; reason?: string }) => {
    if (ev?.code === WS_PASSWORD_CHANGE_REQUIRED) {
      passwordGate = true;
      log?.("ws.password_change_required");
      onPasswordChangeRequired?.();
      return; // não reconectar: aguarda a troca de senha
    }
    log?.(`ws.close ${ev?.code ?? "?"}`);
    onClose?.(ev?.code ?? 0);
  };

  return {
    close() {
      socket.close();
    },
    stoppedByPasswordGate() {
      return passwordGate;
    },
  };
}

/** Backoff exponencial limitado (ms) para reconexão — sem jitter para testar. */
export function reconnectDelay(attempt: number, baseMs = 1_000, maxMs = 30_000): number {
  const exp = baseMs * 2 ** Math.max(0, attempt);
  return Math.min(exp, maxMs);
}
