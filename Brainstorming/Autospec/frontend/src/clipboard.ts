import { t } from "./i18n/i18n";
import { notify } from "./toast";

// Q7 — assisted copy with toast feedback. `navigator.clipboard` needs a secure
// context (https/localhost); the hidden-textarea fallback covers plain-http
// LAN access to the backend.
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      if (!ok) throw new Error("execCommand copy failed");
    }
    notify("success", t("common.copied"));
    return true;
  } catch {
    notify("error", t("common.copyFailed"));
    return false;
  }
}
