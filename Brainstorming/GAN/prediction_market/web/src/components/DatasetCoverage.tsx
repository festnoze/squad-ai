import type { DatasetCoverage as Coverage } from "../types";
import { count, date } from "../util";

export function DatasetCoverage({ coverage }: { coverage: Coverage }) {
  const resolved = coverage.label_status_counts.resolved ?? 0;
  const censored = Object.entries(coverage.label_status_counts)
    .filter(([status]) => status !== "resolved")
    .reduce((total, [, value]) => total + value, 0);
  return <details className="panel coverage-report">
    <summary><span><span className="eyebrow">COUVERTURE DU CORPUS</span><strong>Ce que l’archive permet réellement d’étudier</strong></span><span className="summary-hint">Voir les inconnues</span></summary>
    <div className="coverage-grid">
      <div><span>Conditions sélectionnées</span><strong>{count(coverage.selected_conditions)}</strong><small>sur {count(coverage.population_conditions)} conditions observées</small></div>
      <div><span>Résolutions vérifiées</span><strong>{count(resolved)}</strong><small>{count(coverage.settled_adapter_markets)} marchés utilisables par le moteur</small></div>
      <div><span>Censurées ou sans label</span><strong>{count(censored)}</strong><small>conservées dans l’archive, hors scores de résultat</small></div>
      <div><span>Heures de prix observées</span><strong>{count(coverage.selected_observed_hours)}</strong><small>du {date(coverage.start_ms)} au {date(coverage.end_ms)}</small></div>
    </div>
    <div className="coverage-unknowns">
      <div><i className={coverage.known_historical_close ? "known" : "unknown"} /><p><strong>Heures de clôture historiques</strong>{coverage.known_historical_close ? "Vérifiées dans la source." : "Inconnues : la fin observée ne doit pas être lue comme une échéance contractuelle."}</p></div>
      <div><i className={coverage.verified_event_groups > 0 ? "known" : "unknown"} /><p><strong>Groupes d’événements</strong>{coverage.verified_event_groups > 0 ? `${count(coverage.verified_event_groups)} groupes vérifiés.` : "Inconnus : plusieurs marchés peuvent dépendre du même événement. Leur indépendance n’est pas établie."}</p></div>
      <div><i className={coverage.historical_fee_schedule_known ? "known" : "scenario"} /><p><strong>Frais d’exécution</strong>{coverage.historical_fee_schedule_known ? `Barème historique ${coverage.fee_schedule_id}.` : coverage.fee_schedule_id === "polymarket-research-2026-04" ? "Scénario de 20 points de base par exécution. Le barème historique et les coûts réels complets restent inconnus." : `Scénario ${coverage.fee_schedule_id} ; barème historique non vérifié.`}</p></div>
    </div>
    <p className="coverage-note">Les marchés censurés documentent le périmètre mais ne reçoivent pas un résultat inventé. Les résultats de campagne sont conditionnels aux marchés résolus utilisables et à ce scénario de coûts.</p>
  </details>;
}
