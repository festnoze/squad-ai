import { useI18n } from "../i18n/i18n";

export type MobilePane = "rail" | "scene";

/**
 * R5 — bottom tab bar shown only under 1100px (CSS-gated). Toggles which of the
 * two stacked workspace columns is visible so narrow viewports show one pane at
 * a time instead of one very long scroll: "rail" = chat + planning panels,
 * "scene" = board/activity + run panel.
 */
export function MobileNav({
  pane,
  onChange,
}: {
  pane: MobilePane;
  onChange: (pane: MobilePane) => void;
}) {
  const { t } = useI18n();
  return (
    <nav className="mobile-nav" role="tablist" aria-label={t("mobileNav.ariaLabel")}>
      <button
        type="button"
        role="tab"
        aria-selected={pane === "rail"}
        className={`mobile-nav-tab${pane === "rail" ? " active" : ""}`}
        data-testid="mobile-nav-rail"
        onClick={() => onChange("rail")}
      >
        💬 {t("mobileNav.rail")}
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={pane === "scene"}
        className={`mobile-nav-tab${pane === "scene" ? " active" : ""}`}
        data-testid="mobile-nav-scene"
        onClick={() => onChange("scene")}
      >
        🧱 {t("mobileNav.scene")}
      </button>
    </nav>
  );
}
