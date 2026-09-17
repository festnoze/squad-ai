import { useEffect, useState } from "react";
import { api } from "./api";
import { Explorer } from "./components/Explorer";
import { Experiments } from "./components/Experiments";
import { Discovery } from "./components/Discovery";
import { SignalStudies } from "./components/SignalStudies";
import { BeginnerGuide } from "./components/BeginnerGuide";
import type { View } from "./components/BeginnerGuide";
import { DatasetCoverage } from "./components/DatasetCoverage";
import type { AgentSummary, DatasetSummary } from "./types";
import { count, date, errorMessage, providerName, remember, stored } from "./util";

export function App() {
  const savedView = stored("pmx.view");
  const [view, setView] = useState<View>(savedView === "experiments" || savedView === "discovery" || savedView === "signals" ? savedView : "explorer");
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [datasetName, setDatasetName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [requestedRun, setRequestedRun] = useState("");
  useEffect(() => {
    let current = true; setLoading(true); setError("");
    Promise.all([api.datasets(), api.agents()]).then(([data, registry]) => {
      if (!current) return;
      setDatasets(data.datasets); setAgents(registry.agents);
      setDatasetName(previous => {
        if (data.datasets.some(dataset => dataset.name === previous)) return previous;
        const polymarketArchive = data.datasets
          .filter(dataset => dataset.coverage && dataset.providers.includes("polymarket"))
          .sort((left, right) => (right.coverage?.end_ms ?? Date.parse(right.freeze_date)) - (left.coverage?.end_ms ?? Date.parse(left.freeze_date)))[0];
        return polymarketArchive?.name ?? data.datasets.find(dataset => dataset.name === "mvp2026")?.name ?? data.datasets[0]?.name ?? "";
      });
    }).catch(error => { if (current) setError(errorMessage(error)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [reload]);
  const dataset = datasets.find(item => item.name === datasetName);
  const navigate = (next: View) => { setView(next); remember("pmx.view", next); };
  const inspectRun = (runId: string) => { setRequestedRun(runId); remember("pmx.selectedRun", runId); navigate("experiments"); };
  return <div className="app">
    <a href="#main-content" className="skip-link">Aller au contenu</a>
    <header className="topbar"><div className="topbar-inner"><a className="brand" href="#" onClick={event => { event.preventDefault(); navigate("explorer"); }} aria-label="pmx, accueil"><span className="brand-symbol" aria-hidden="true">p<span>m</span>x<span className="brand-dot">.</span></span><span className="brand-caption">ATELIER DE RECHERCHE</span></a><nav aria-label="Navigation principale"><button className={view === "explorer" ? "active" : ""} onClick={() => navigate("explorer")}>Explorer</button><button className={view === "signals" ? "active" : ""} onClick={() => navigate("signals")}>Signaux</button><button className={view === "discovery" ? "active" : ""} onClick={() => navigate("discovery")}>Découvrir</button><button className={view === "experiments" ? "active" : ""} onClick={() => navigate("experiments")}>Expériences</button></nav><div className="local-state"><i className={error ? "offline" : ""} />{error ? "Serveur indisponible" : loading ? "Connexion…" : "Environnement local"}</div></div></header>
    <main id="main-content" className="main-content">
      <section className="hero"><div><span className="eyebrow">MARCHÉS PRÉDICTIFS / LABORATOIRE LOCAL</span><h1>Observer. Comparer. <em>Comprendre.</em></h1><p>Un atelier pour mettre les stratégies à l'épreuve des données, et distinguer une bonne prévision d'un gain simulé.</p></div><div className="hero-aside"><span className="version-pill">MVP · PREMIÈRE EXPÉRIMENTATION</span><div className="research-note"><span className="research-mark">↗</span><p><strong>Une preuve se construit.</strong>Les résultats sont exploratoires. Chaque décision reste inspectable et chaque expérience reproductible.</p></div></div></section>
      <BeginnerGuide navigate={navigate} />
      {loading && <div className="panel empty"><span className="loader" />Vérification des données réelles… Le premier chargement d'une archive peut prendre plusieurs minutes.</div>}
      {error && <div className="panel unavailable" role="alert"><h2>Connexion au serveur impossible</h2><p>{error}</p><p>Démarrez l'application avec le lanceur du projet, puis réessayez. Aucun jeu de démonstration n'est substitué aux données.</p><button className="button primary" onClick={() => setReload(r => r + 1)}>Réessayer la connexion</button></div>}
      {!loading && !error && !dataset && <div className="panel unavailable"><h2>Aucun jeu de données disponible</h2><p>Préparez le jeu <code>mvp2026</code> à partir des données locales avec la commande de préparation indiquée dans le README, puis actualisez cette page.</p><p>Les données originales sont conservées. Aucune donnée artificielle ne sera affichée.</p><button className="button primary" onClick={() => setReload(r => r + 1)}>Actualiser les données</button></div>}
      {dataset && !error && <>
        <section className="dataset-strip panel" aria-label="Résumé du jeu de données"><div className="dataset-identity"><span className="eyebrow">JEU DE DONNÉES ACTIF</span>{datasets.length > 1 ? <select value={datasetName} onChange={e => setDatasetName(e.target.value)} aria-label="Jeu de données actif">{datasets.map(d => <option key={d.name}>{d.name}</option>)}</select> : <strong>{dataset.name}</strong>}<span>Figé le {date(dataset.freeze_date)}</span></div><div className="dataset-stat"><strong>{count(dataset.n_visible_markets)}</strong><span>marchés explorables</span></div><div className="dataset-stat"><strong>{count(dataset.counts_by_fold.train ?? 0)} <small>/</small> {count(dataset.counts_by_fold.validation ?? 0)}</strong><span>entraînement / validation</span></div><div className="dataset-stat"><strong>{dataset.interval_min === 1440 ? "1 jour" : `${dataset.interval_min} min`}</strong><span>pas de temps · latence simulée</span></div><div className="dataset-platforms">{dataset.providers.map(p => <span key={p}><i />{providerName(p)} <strong>{count(dataset.counts_by_provider[p] ?? 0)}</strong></span>)}</div></section>
        <details className="dataset-limitations"><summary><span className="notice-icon">i</span> Périmètre et limites des données <span className="summary-hint">Consulter la provenance</span></summary><div><p>{count(dataset.n_markets)} marchés dans le jeu complet. Le navigateur et les expériences n'utilisent que les échantillons d'entraînement et de validation ; le scellé reste exclu. Les nombres par plateforme concernent les marchés explorables.</p><ul>{dataset.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul><p>Empreinte du jeu : <code>{dataset.dataset_hash}</code></p></div></details>
        {dataset.coverage && <DatasetCoverage coverage={dataset.coverage} />}
        {view === "signals" && <SignalStudies key={dataset.name} dataset={dataset} />}
        <div hidden={view !== "explorer"}><Explorer key={dataset.name} dataset={dataset} onExperiment={() => navigate("experiments")} /></div>
        <div hidden={view !== "discovery"}><Discovery key={dataset.name} dataset={dataset} onInspectRun={inspectRun} /></div>
        <div hidden={view !== "experiments"}><Experiments key={dataset.name} dataset={dataset} agents={agents} requestedRun={requestedRun} /></div>
      </>}
      <footer className="app-footer"><span><strong>pmx</strong> / Atelier de recherche</span><span>Données historiques · Heure UTC · Aucun ordre réel</span></footer>
    </main>
  </div>;
}
