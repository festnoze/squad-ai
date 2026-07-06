import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n/i18n";
import { useEscapeToClose } from "../hooks";

// Q2 — branded replacement for window.confirm(). One <ConfirmHost/> is mounted
// in App; `confirmAction()` is awaitable from anywhere (components, handlers)
// and resolves true/false. Falls back to the native confirm if the host is not
// mounted (tests rendering a component in isolation keep working).

export interface ConfirmOptions {
  title: string;
  body?: string;
  confirmLabel?: string;
  danger?: boolean;
}

interface PendingConfirm extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

let host: ((pending: PendingConfirm) => void) | null = null;

export function confirmAction(opts: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    if (!host) {
      resolve(window.confirm(opts.body ?? opts.title));
      return;
    }
    host({ ...opts, resolve });
  });
}

export function ConfirmHost() {
  const { t } = useI18n();
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  useEffect(() => {
    host = setPending;
    return () => {
      host = null;
    };
  }, []);

  const close = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
  };
  useEscapeToClose(pending !== null, () => close(false));

  // Autofocus Cancel — the safe default for destructive actions.
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (pending) cancelRef.current?.focus();
  }, [pending]);

  if (!pending) return null;
  return (
    <div className="modal-backdrop" onClick={() => close(false)}>
      <div
        className="modal confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={pending.title}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            close(true);
          }
        }}
      >
        <h2>{pending.title}</h2>
        {pending.body && <p className="confirm-body">{pending.body}</p>}
        <div className="confirm-actions">
          <button ref={cancelRef} type="button" className="ghost" onClick={() => close(false)}>
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className={pending.danger ? "danger" : "primary"}
            data-testid="confirm-accept"
            onClick={() => close(true)}
          >
            {pending.confirmLabel ?? t("common.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
