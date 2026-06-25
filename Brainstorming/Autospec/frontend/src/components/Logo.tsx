interface Props {
  /** Pixel size of the square mark. Defaults to 1.1em via CSS class. */
  size?: number;
  className?: string;
}

/**
 * Autospec brand mark: code brackets `< >` wrapped around an AI spark.
 * Brackets inherit `currentColor` (so they adapt to the theme); the spark uses
 * the accent token for a two-tone pop. Decorative — labelled for a11y.
 */
export function Logo({ size, className }: Props) {
  return (
    <svg
      className={`app-logo${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Autospec"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* code brackets */}
      <path
        d="M12 8 L5 16 L12 24"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M20 8 L27 16 L20 24"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* AI spark */}
      <path
        d="M16 10 L17.5 14.5 L22 16 L17.5 17.5 L16 22 L14.5 17.5 L10 16 L14.5 14.5 Z"
        fill="var(--accent)"
      />
    </svg>
  );
}
