import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { listMessages, sendMessage } from '../../api/chat';
import type {
  ChatMessage,
  Item,
  ScopingAction,
  SendMessageResponse,
} from '../../types/chat';
import ErrorBox from '../ErrorBox';

interface ChatProps {
  projectId: string;
  // Fired whenever the backend reports that items were created or updated
  // as a side-effect of a chat message. The parent uses this to refresh the
  // items panel on the left without coupling it to the chat state.
  onItemsChanged?: () => void;
}

// Extra UI metadata attached to a displayed message (optimistic state,
// scoping action feedback, etc.). Kept out of ChatMessage so the type stays
// aligned with the backend contract.
interface DisplayedMessage extends ChatMessage {
  _optimistic?: boolean;
  _actionInfo?: ActionInfo | null;
}

interface ActionInfo {
  action: ScopingAction;
  itemsCreated: Item[];
  itemsUpdated: Item[];
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function countByType(items: Item[]): {
  epics: number;
  userStories: number;
  tasks: number;
} {
  let epics = 0;
  let userStories = 0;
  let tasks = 0;
  for (const it of items) {
    if (it.type === 'epic') epics += 1;
    else if (it.type === 'user_story') userStories += 1;
    else if (it.type === 'task') tasks += 1;
  }
  return { epics, userStories, tasks };
}

function renderActionInfo(info: ActionInfo): string | null {
  if (info.action === 'propose_items' && info.itemsCreated.length > 0) {
    const { epics, userStories, tasks } = countByType(info.itemsCreated);
    const parts: string[] = [];
    if (epics > 0) parts.push(`${epics} epic${epics > 1 ? 's' : ''}`);
    if (userStories > 0)
      parts.push(`${userStories} user stor${userStories > 1 ? 'ies' : 'y'}`);
    if (tasks > 0) parts.push(`${tasks} tache${tasks > 1 ? 's' : ''}`);
    const detail = parts.length > 0 ? ` (${parts.join(', ')})` : '';
    return `[items] ${info.itemsCreated.length} items proposes${detail}`;
  }
  if (info.action === 'confirm' && info.itemsUpdated.length > 0) {
    return `[ok] ${info.itemsUpdated.length} items confirmes`;
  }
  return null;
}

function Chat({ projectId, onItemsChanged }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sending, setSending] = useState<boolean>(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [input, setInput] = useState<string>('');

  // Optimistic state is kept outside `messages` (which mirrors the real
  // server history after each send). A single pending user message is
  // displayed between the POST and the refetch.
  const [pendingUser, setPendingUser] = useState<DisplayedMessage | null>(
    null,
  );

  // Action info (scoping action + counts) is attached by id to the
  // assistant messages after a successful send. It survives the refetch
  // because it lives in a separate map keyed by the backend-provided id.
  const [actionInfoById, setActionInfoById] = useState<
    Record<string, ActionInfo>
  >({});

  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Bumping this key forces the load effect to re-run (Retry button,
  // and implicit refetch after a successful send via `ahandleSend`).
  const [reloadKey, setReloadKey] = useState<number>(0);

  // Load the chat history whenever the projectId changes (or when the
  // user hits "Réessayer", which bumps `reloadKey`). We use a `cancelled`
  // flag so that navigating rapidly between two projects never lets a
  // late response from project X overwrite the state of project Y — one
  // of the classic React data-fetching race bugs.
  useEffect(() => {
    let cancelled = false;

    async function aloadHistory(): Promise<void> {
      setLoading(true);
      setLoadError(null);
      setMessages([]);
      setPendingUser(null);
      setActionInfoById({});
      try {
        const data = await listMessages(projectId);
        if (cancelled) return;
        setMessages(data);
      } catch (err) {
        if (cancelled) return;
        setLoadError(
          err instanceof Error
            ? err.message
            : 'Impossible de charger l\'historique',
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void aloadHistory();

    return () => {
      cancelled = true;
    };
  }, [projectId, reloadKey]);

  // Auto-scroll to bottom whenever the displayed message count changes
  // (server messages OR the pending optimistic user message).
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, pendingUser]);

  async function ahandleSend(): Promise<void> {
    const content = input.trim();
    if (content === '' || sending) return;

    const tempId = `temp-${Date.now()}`;
    const optimistic: DisplayedMessage = {
      id: tempId,
      project_id: projectId,
      role: 'user',
      content,
      meta_data: null,
      created_at: new Date().toISOString(),
      _optimistic: true,
    };

    setPendingUser(optimistic);
    setInput('');
    setSending(true);
    setSendError(null);

    try {
      const response: SendMessageResponse = await sendMessage(projectId, {
        content,
      });

      // Attach the action info to the assistant message id so it survives
      // the refetch (which replaces `messages` wholesale with server data).
      setActionInfoById((prev) => ({
        ...prev,
        [response.message.id]: {
          action: response.action,
          itemsCreated: response.items_created,
          itemsUpdated: response.items_updated,
        },
      }));

      // Notify the parent so the items panel on the left can refresh. We
      // only fire when the backend actually reports a change, to avoid
      // useless reloads on pure conversation turns.
      if (
        onItemsChanged &&
        (response.items_created.length > 0 ||
          response.items_updated.length > 0)
      ) {
        onItemsChanged();
      }

      // Refetch the full history from the server so both the user and the
      // assistant messages come with their real UUIDs + timestamps, and
      // there is no risk of an orphan optimistic message sticking around
      // with a fake `temp-*-sent` id after a future refresh.
      const fresh = await listMessages(projectId);
      setMessages(fresh);
      setPendingUser(null);
    } catch (err) {
      // Drop the optimistic message on failure and surface the error.
      setPendingUser(null);
      setSendError(
        err instanceof Error ? err.message : 'Erreur lors de l\'envoi',
      );
      // Restore input so the user can retry without retyping.
      setInput(content);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void ahandleSend();
    }
  }

  return (
    <div className="flex h-full w-full flex-col bg-white">
      {/* Header */}
      <div className="flex h-12 flex-shrink-0 items-center border-b border-gray-200 px-4 font-semibold text-gray-800">
        Chat de cadrage
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-3"
      >
        {loading && (
          <p className="text-center text-sm text-gray-500">
            Chargement de l'historique...
          </p>
        )}

        {!loading && loadError && (
          <ErrorBox
            message={loadError}
            onRetry={() => setReloadKey((k) => k + 1)}
            size="sm"
          />
        )}

        {!loading &&
          !loadError &&
          messages.length === 0 &&
          pendingUser === null && (
            <p className="text-center text-sm text-gray-400">
              Decrivez votre projet pour commencer...
            </p>
          )}

        {!loading &&
          (() => {
            // Combine the real server messages with the (optional) pending
            // optimistic user message. The pending message is always
            // displayed last because it is the one being sent right now.
            const displayed: DisplayedMessage[] = messages.map((m) => ({
              ...m,
              _actionInfo: actionInfoById[m.id] ?? null,
            }));
            if (pendingUser) {
              displayed.push(pendingUser);
            }
            return displayed.map((msg) => {
              if (msg.role === 'system') {
                return (
                  <div key={msg.id} className="text-center">
                    <p className="text-xs italic text-gray-500">
                      {msg.content}
                    </p>
                  </div>
                );
              }

              const isUser = msg.role === 'user';
              const bubbleClasses = isUser
                ? 'ml-auto bg-blue-500 text-white'
                : 'mr-auto bg-gray-100 text-gray-800';
              const alignClasses = isUser ? 'items-end' : 'items-start';
              const actionLabel = msg._actionInfo
                ? renderActionInfo(msg._actionInfo)
                : null;

              return (
                <div key={msg.id} className={`flex flex-col ${alignClasses}`}>
                  <div
                    className={`max-w-[280px] whitespace-pre-wrap break-words rounded-lg px-3 py-2 text-sm ${bubbleClasses}`}
                  >
                    {msg.content}
                  </div>
                  {actionLabel && (
                    <div className="mt-1 max-w-[280px] rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-700">
                      {actionLabel}
                    </div>
                  )}
                  <div className="mt-0.5 text-xs text-gray-500">
                    {formatTime(msg.created_at)}
                    {msg._optimistic && (
                      <span className="ml-1 italic">
                        - en cours d'envoi...
                      </span>
                    )}
                  </div>
                </div>
              );
            });
          })()}
      </div>

      {/* Send error banner */}
      {sendError && (
        <div className="flex-shrink-0 border-t border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <div className="flex items-start justify-between gap-2">
            <span>Erreur: {sendError}</span>
            <button
              type="button"
              onClick={() => setSendError(null)}
              className="text-red-700 hover:underline"
            >
              Fermer
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="flex-shrink-0 border-t border-gray-200 p-3">
        <div className="flex items-end gap-2">
          <label htmlFor="chat-input" className="sr-only">
            Message pour l'agent de cadrage
          </label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Tapez votre message..."
            rows={2}
            disabled={sending}
            className="flex-1 resize-none rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
          />
          <button
            type="button"
            onClick={() => void ahandleSend()}
            disabled={sending || input.trim() === ''}
            className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sending ? '...' : 'Envoyer'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default Chat;
