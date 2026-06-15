import { ProductComponent } from "../types";
import { CollapsibleSection } from "./CollapsibleSection";

const KIND_ICON: Record<string, string> = {
  backend: "⚙️",
  frontend: "🖥️",
  database: "🗄️",
  cache: "⚡",
  other: "📦",
};

const STATUS_LABEL: Record<string, string> = {
  proposed: "proposé",
  approved: "approuvé",
  created: "créé",
  rejected: "écarté",
};

interface Props {
  components: ProductComponent[];
  onUpdate: (components: ProductComponent[]) => void;
  onSetup: () => void;
}

/** Composants du produit proposés par l'agent solutionneur : l'utilisateur
 * approuve/écarte chaque composant, puis lance la création réelle (setup). */
export function ComponentsPanel({ components, onUpdate, onSetup }: Props) {
  if (components.length === 0) return null;

  const toggle = (target: ProductComponent) => {
    if (target.status === "created") return; // déjà matérialisé
    const next = components.map((c) =>
      c.id === target.id
        ? {
            ...c,
            status: (c.status === "approved" ? "rejected" : "approved") as
              | "approved"
              | "rejected",
          }
        : c,
    );
    onUpdate(next);
  };

  const approvedCount = components.filter(
    (c) => c.status === "approved" || c.status === "created",
  ).length;

  return (
    <CollapsibleSection title="🧱 Composants du produit" className="components">
      <div className="component-list">
        {components.map((c) => (
          <div key={c.id} className={`component status-${c.status}`}>
            <span className="component-icon">{KIND_ICON[c.kind] ?? "📦"}</span>
            <span className="component-name">
              {c.name}
              <span className="component-tech"> — {c.technology}</span>
              {c.optional && <span className="component-optional"> (optionnel)</span>}
            </span>
            <span className={`state-tag component-status-${c.status}`}>
              {STATUS_LABEL[c.status] ?? c.status}
            </span>
            {c.status !== "created" && (
              <button
                className="small-btn"
                title={c.status === "approved" ? "Écarter ce composant" : "Approuver ce composant"}
                onClick={() => toggle(c)}
              >
                {c.status === "approved" ? "✕" : "✓"}
              </button>
            )}
          </div>
        ))}
      </div>
      <button
        className="primary setup-btn"
        disabled={approvedCount === 0}
        onClick={onSetup}
        title="Créer réellement les composants approuvés (dossiers, manifests)"
      >
        🧱 Créer les composants approuvés
      </button>
    </CollapsibleSection>
  );
}
