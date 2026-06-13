import { useEffect, useRef, useState } from "react";
import { ChatMessage, PipelinePhase } from "../types";

const ROLE_LABEL: Record<string, string> = {
  user: "Toi",
  pm: "📋 PM",
  po: "🏃 PO",
  dev: "💻 Dev",
  analyst: "🔍 Analyste",
  architect: "🏛️ Architecte",
  qa: "🧪 QA",
  critic: "🧐 Critique",
  judge: "⚖️ Juge",
  system: "⚙️ Système",
};

interface Props {
  chat: ChatMessage[];
  phase: PipelinePhase;
  onSend: (message: string) => void;
  specMode: "interview" | "brainstorm";
  onSetSpecMode: (mode: "interview" | "brainstorm") => void;
}

export function ChatPanel({ chat, phase, onSend, specMode, onSetSpecMode }: Props) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

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
      ? "Réponds au PM…"
      : phase === "build" || phase === "architect"
        ? "Donne une consigne au dev en cours… (prise en compte aux prochaines tentatives)"
        : "Donne ton feedback sur l'itération en cours…";

  return (
    <div className="panel chat">
      <div className="chat-header">
        <h2>Chat — spécification &amp; feedback</h2>
        {phase === "spec" && (
          <div
            className="spec-mode-switch"
            role="group"
            aria-label="Mode de spécification"
          >
            <button
              type="button"
              className={`spec-mode-btn${specMode === "interview" ? " active" : ""}`}
              aria-pressed={specMode === "interview"}
              title="Interview socratique : clarifier le besoin par une série de questions ciblées, dimension par dimension."
              onClick={() => onSetSpecMode("interview")}
            >
              💬 Interview
            </button>
            <button
              type="button"
              className={`spec-mode-btn${specMode === "brainstorm" ? " active" : ""}`}
              aria-pressed={specMode === "brainstorm"}
              title="Brainstorming : le PM/analyste re-questionne lui-même le besoin (divergence puis convergence)."
              onClick={() => onSetSpecMode("brainstorm")}
            >
              🧠 Brainstorming
            </button>
          </div>
        )}
      </div>
      <div className="chat-messages">
        {chat.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            <span className="msg-role">{ROLE_LABEL[m.role] ?? m.role}</span>
            <pre>{m.content}</pre>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
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
          Envoyer
        </button>
      </div>
    </div>
  );
}
