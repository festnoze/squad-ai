import { ReactNode, useState } from "react";

/**
 * Panneau repliable (UI5) : en-tête cliquable (caret + titre) qui plie/déplie le
 * contenu. Les panneaux latéraux (Composants/Backlog/Architecture) s'affichent
 * déjà uniquement quand ils ont du contenu ; ceci permet en plus de les replier
 * quand la colonne de gauche se charge.
 */
export function CollapsibleSection({
  title,
  className,
  defaultOpen = true,
  headerExtra,
  children,
}: {
  title: string;
  className: string;
  defaultOpen?: boolean;
  headerExtra?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`panel ${className}${open ? "" : " panel-collapsed"}`}>
      <button
        type="button"
        className="panel-header-btn"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="panel-caret" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <h2>{title}</h2>
        {headerExtra}
      </button>
      {open && <div className="panel-body">{children}</div>}
    </div>
  );
}
