import { useEffect, useRef, useState } from "react";
import { ChatMessage, PipelinePhase } from "../types";

const ROLE_LABEL: Record<string, string> = {
  user: "Toi",
  pm: "📋 PM",
  po: "🏃 PO",
  dev: "💻 Dev",
  analyst: "🔍 Analyste",
  qa: "🧪 QA",
  system: "⚙️ Système",
};

interface Props {
  chat: ChatMessage[];
  phase: PipelinePhase;
  onSend: (message: string) => void;
}

export function ChatPanel({ chat, phase, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.length]);

  const send = () => {
    if (!draft.trim()) return;
    onSend(draft);
    setDraft("");
  };

  const placeholder =
    phase === "spec"
      ? "Réponds au PM…"
      : "Donne ton feedback sur l'itération en cours…";

  return (
    <div className="panel chat">
      <h2>Chat — spécification &amp; feedback</h2>
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
