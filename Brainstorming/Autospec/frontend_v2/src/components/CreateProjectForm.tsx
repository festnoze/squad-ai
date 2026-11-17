import { useState, type FormEvent } from "react";
import { createProject, type CreateProjectBody, type Profile, type ProjectSummary } from "../api";
import { PROFILE_LABELS } from "../format";

type Source = "brief" | "goal";

const PROFILES = Object.keys(PROFILE_LABELS) as Profile[];

/** Creation form: POST /api/v2/projects, the build starts at once on the server. */
export function CreateProjectForm({ onCreated }: { onCreated: (project: ProjectSummary) => void }) {
  const [name, setName] = useState("");
  const [profile, setProfile] = useState<Profile | "">("");
  const [source, setSource] = useState<Source>("brief");
  const [text, setText] = useState("");
  const [pkg, setPkg] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return setError("Le nom est obligatoire.");
    if (!text.trim()) {
      return setError(source === "brief" ? "Le brief est obligatoire." : "L'objectif est obligatoire.");
    }
    const body: CreateProjectBody = { name: name.trim(), [source]: text.trim() };
    if (profile) body.profile = profile;
    if (pkg.trim()) body.package = pkg.trim();
    if (model.trim()) body.model = model.trim();
    setError("");
    setSubmitting(true);
    try {
      onCreated(await createProject(body));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card create-form" onSubmit={onSubmit} aria-labelledby="create-title" noValidate>
      <h2 id="create-title">Nouveau projet</h2>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="project-name">Nom</label>
          <input
            id="project-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoComplete="off"
          />
        </div>
        <div className="field">
          <label htmlFor="project-profile">Profil</label>
          <select id="project-profile" value={profile} onChange={(e) => setProfile(e.target.value as Profile | "")}>
            <option value="">Choisi par le PO</option>
            {PROFILES.map((value) => (
              <option key={value} value={value}>
                {PROFILE_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="field">
        <legend>Point de départ</legend>
        <label className="inline">
          <input type="radio" name="source" checked={source === "brief"} onChange={() => setSource("brief")} />
          Brief détaillé
        </label>
        <label className="inline">
          <input type="radio" name="source" checked={source === "goal"} onChange={() => setSource("goal")} />
          Objectif (le PM rédige le brief)
        </label>
      </fieldset>

      <div className="field">
        <label htmlFor="project-text">{source === "brief" ? "Brief" : "Objectif"}</label>
        <textarea
          id="project-text"
          rows={source === "brief" ? 10 : 3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
      </div>

      <details className="advanced">
        <summary>Options avancées</summary>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="project-package">Paquet Python</label>
            <input
              id="project-package"
              value={pkg}
              onChange={(e) => setPkg(e.target.value)}
              placeholder="déduit du nom"
              autoComplete="off"
            />
          </div>
          <div className="field">
            <label htmlFor="project-model">Modèle</label>
            <input
              id="project-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="celui du serveur"
              autoComplete="off"
            />
          </div>
        </div>
      </details>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? "Création..." : "Créer et lancer"}
        </button>
      </div>
    </form>
  );
}
