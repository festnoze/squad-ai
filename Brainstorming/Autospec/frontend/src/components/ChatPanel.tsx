import { useEffect, useRef, useState } from "react";
import { ChatMessage, PipelinePhase } from "../types";
import { useI18n } from "../i18n/i18n";

interface Props {
  chat: ChatMessage[];
  phase: PipelinePhase;
  onSend: (message: string) => void;
  specMode: "interview" | "brainstorm";
  onSetSpecMode: (mode: "interview" | "brainstorm") => void;
  // B-IDEA: a vague idea was detected — offer a brainstorming session.
  awaitingBrainstorm?: boolean;
  brainstormTechniques?: string[];
  onResolveBrainstorm?: (accept: boolean) => void;
}

export function ChatPanel({
  chat,
  phase,
  onSend,
  specMode,
  onSetSpecMode,
  awaitingBrainstorm = false,
  brainstormTechniques = [],
  onResolveBrainstorm,
}: Props) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const ROLE_LABEL: Record<string, string> = {
    user: t("chatPanel.roleUser"),
    pm: t("chatPanel.rolePm"),
    po: t("chatPanel.rolePo"),
    dev: t("chatPanel.roleDev"),
    analyst: t("chatPanel.roleAnalyst"),
    architect: t("chatPanel.roleArchitect"),
    qa: t("chatPanel.roleQa"),
    critic: t("chatPanel.roleCritic"),
    judge: t("chatPanel.roleJudge"),
    system: t("chatPanel.roleSystem"),
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.length]);

  const send = () => {
    const message = draft.trim();
    if (!message) return;
    onSend(message);
    setDraft("");
  };

  const placeholder =
    phase === "spec"
      ? t("chatPanel.placeholderSpec")
      : phase === "build" || phase === "architect"
        ? t("chatPanel.placeholderBuild")
        : t("chatPanel.placeholderFeedback");

  return (
    <div className="panel chat">
      <div className="chat-header">
        <h2>{t("chatPanel.heading")}</h2>
        {phase === "spec" && (
          <div
            className="spec-mode-switch"
            role="group"
            aria-label={t("chatPanel.specModeGroup")}
          >
            <button
              type="button"
              className={`spec-mode-btn${specMode === "interview" ? " active" : ""}`}
              aria-pressed={specMode === "interview"}
              title={t("chatPanel.interviewTitle")}
              onClick={() => onSetSpecMode("interview")}
            >
              {t("chatPanel.interview")}
            </button>
            <button
              type="button"
              className={`spec-mode-btn${specMode === "brainstorm" ? " active" : ""}`}
              aria-pressed={specMode === "brainstorm"}
              title={t("chatPanel.brainstormingTitle")}
              onClick={() => onSetSpecMode("brainstorm")}
            >
              {t("chatPanel.brainstorming")}
            </button>
          </div>
        )}
      </div>
      <div className="chat-messages">
        {chat.length === 0 ? (
          <div className="chat-empty">
            <p className="placeholder">
              {phase === "spec"
                ? t("chatPanel.emptySpec")
                : t("chatPanel.emptyBuild")}
            </p>
          </div>
        ) : (
          chat.map((m, i) => (
            <div key={i} className={`msg msg-${m.role}`}>
              <span className="msg-role">{ROLE_LABEL[m.role] ?? m.role}</span>
              <pre>{m.content}</pre>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
      {awaitingBrainstorm && onResolveBrainstorm && (
        <div className="brainstorm-offer" role="group" aria-label={t("chatPanel.brainstormOfferGroup")}>
          <p>
            {t("chatPanel.brainstormOfferLead")}
            <strong>{t("chatPanel.brainstormOfferWord")}</strong>
            {t("chatPanel.brainstormOfferTrail")}
            {brainstormTechniques.length > 0 && (
              <span className="brainstorm-tech">
                {t("chatPanel.brainstormTechniques", { list: brainstormTechniques.join(", ") })}
              </span>
            )}
          </p>
          <div className="brainstorm-actions">
            <button
              type="button"
              className="brainstorm-btn accept"
              onClick={() => onResolveBrainstorm(true)}
            >
              {t("chatPanel.brainstormAccept")}
            </button>
            <button
              type="button"
              className="brainstorm-btn refuse"
              onClick={() => onResolveBrainstorm(false)}
            >
              {t("chatPanel.brainstormRefuse")}
            </button>
          </div>
        </div>
      )}
      <div className="chat-input">
        <textarea
          rows={2}
          placeholder={placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button onClick={send} disabled={!draft.trim()}>
          {t("chatPanel.send")}
        </button>
      </div>
    </div>
  );
}
