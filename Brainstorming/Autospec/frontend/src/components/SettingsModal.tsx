import { LANGS, useI18n } from "../i18n/i18n";
import { useTheme } from "../i18n/theme";

interface Props {
  onClose: () => void;
}

/**
 * Parameters window: lets the user switch the color theme (dark/light) and the
 * interface language (en/fr). Both preferences are persisted to localStorage by
 * the underlying stores and applied app-wide instantly.
 */
export function SettingsModal({ onClose }: Props) {
  const { t, lang, setLang } = useI18n();
  const { theme, setTheme } = useTheme();

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal settings-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("settings.title")}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="modal-close"
          title={t("common.close")}
          aria-label={t("common.close")}
          onClick={onClose}
        >
          ✕
        </button>
        <h2>⚙️ {t("settings.title")}</h2>

        <section className="settings-section">
          <div className="settings-section-title">{t("settings.appearance")}</div>
          <p className="settings-hint">{t("settings.themeHint")}</p>
          <div className="settings-row">
            <span className="settings-row-label">{t("settings.theme")}</span>
            <div className="settings-segmented" role="group" aria-label={t("settings.theme")}>
              <button
                type="button"
                aria-pressed={theme === "dark"}
                onClick={() => setTheme("dark")}
              >
                🌙 {t("settings.themeDark")}
              </button>
              <button
                type="button"
                aria-pressed={theme === "light"}
                onClick={() => setTheme("light")}
              >
                ☀️ {t("settings.themeLight")}
              </button>
            </div>
          </div>
        </section>

        <section className="settings-section">
          <div className="settings-section-title">{t("settings.language")}</div>
          <p className="settings-hint">{t("settings.languageHint")}</p>
          <div className="settings-row">
            <span className="settings-row-label">{t("settings.language")}</span>
            <div className="settings-segmented" role="group" aria-label={t("settings.language")}>
              {LANGS.map((l) => (
                <button
                  key={l.value}
                  type="button"
                  aria-pressed={lang === l.value}
                  onClick={() => setLang(l.value)}
                >
                  {l.flag} {l.label}
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
