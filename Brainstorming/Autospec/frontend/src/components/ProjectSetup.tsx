import { useState } from "react";

interface Props {
  onCreate: (goal: string, name: string, autoSpec: boolean, budgetUsd: number, brief?: string, brownfieldPath?: string) => void;
  busy: boolean;
}

export function ProjectSetup({ onCreate, busy }: Props) {
  const [goal, setGoal] = useState("");
  const [name, setName] = useState("");
  const [autoSpec, setAutoSpec] = useState(false);
  const [budget, setBudget] = useState("");
  const [brief, setBrief] = useState("");
  const [brownfield, setBrownfield] = useState("");

  return (
    <div className="panel setup">
      <h2>Nouveau projet / feature</h2>
      <input
        placeholder="Nom du projet (optionnel)"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <textarea
        placeholder="Décris la feature ou le projet que tu veux créer…"
        rows={6}
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
      />
      <label className="autospec-toggle">
        <input
          type="checkbox"
          checked={autoSpec}
          onChange={(e) => setAutoSpec(e.target.checked)}
        />
        <span>
          <strong>Auto-spec</strong> — le PM décide de tout seul et enchaîne les
          itérations en boucle jusqu'à l'arrêt manuel
        </span>
      </label>
      <textarea
        placeholder="Spec à importer (optionnel) — colle un cahier des charges pour court-circuiter l'interview"
        rows={4}
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
      />
      <input
        aria-label="Chemin d'un repo existant à étendre (mode brownfield, optionnel)"
        placeholder="Repo existant à étendre (chemin, optionnel — mode brownfield)"
        value={brownfield}
        onChange={(e) => setBrownfield(e.target.value)}
      />
      <input
        type="number"
        aria-label="Budget maximum en dollars (vide = pas de limite)"
        min={0}
        step={0.1}
        placeholder="Budget max ($) — vide = pas de limite"
        value={budget}
        onChange={(e) => setBudget(e.target.value)}
      />
      <button
        className="primary"
        disabled={busy || !goal.trim()}
        onClick={() => onCreate(goal.trim(), name.trim(), autoSpec, Number(budget) || 0, brief.trim() || undefined, brownfield.trim() || undefined)}
      >
        {autoSpec ? "🔁 Lancer la boucle auto-spec" : "🚀 Démarrer la spécification"}
      </button>
    </div>
  );
}
