interface ErrorBoxProps {
  /** Error message shown to the user. */
  message: string;
  /**
   * Optional retry handler. When provided, a "Reessayer" button is rendered.
   */
  onRetry?: () => void;
  /**
   * Visual size: `"sm"` fits inside tight places (chat input area, inline
   * cells), `"md"` is the default used in main content panels.
   */
  size?: 'sm' | 'md';
}

/**
 * Small red-bordered error panel shared between ProjectList, ProjectView,
 * Chat, ItemDetail and the *View components so every error surface looks
 * and behaves the same way.
 */
function ErrorBox({ message, onRetry, size = 'md' }: ErrorBoxProps) {
  const padding = size === 'sm' ? 'p-3' : 'p-4';
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';
  const buttonPadding = size === 'sm' ? 'px-2 py-1' : 'px-3 py-1.5';
  const buttonText = size === 'sm' ? 'text-xs' : 'text-sm';

  return (
    <div
      role="alert"
      className={`rounded border border-red-200 bg-red-50 ${padding}`}
    >
      <p className={`text-red-700 ${textSize}`}>{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={`mt-2 rounded bg-red-600 font-medium text-white hover:bg-red-700 ${buttonPadding} ${buttonText}`}
        >
          Reessayer
        </button>
      )}
    </div>
  );
}

export default ErrorBox;
