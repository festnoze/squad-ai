import { useState } from "react";
import { remember, stored } from "../util";

export type View = "explorer" | "discovery" | "experiments" | "signals";
const lessons: { title: string; text: string; example: string; view: View; action: string }[] = [
  { title: "1. Lire un marché", view: "explorer", action: "Voir les marchés",
    text: "Un contrat OUI verse 1 unité si l’événement se réalise, 0 sinon. Le prix reflète une probabilité implicite. Dans Explorer, choisissez un marché et observez son prix et son volume.",
    example: "Acheter à 0,90 et gagner rapporte 0,10 avant frais ; perdre coûte 0,90. Un taux de réussite élevé ne suffit donc pas." },
  { title: "2. Chercher un signal", view: "signals", action: "Ouvrir l’étude de signaux",
    text: "Un signal est une observation qui pourrait aider à prévoir la suite : un prix élevé mal calibré, un retournement ou une activité inhabituelle. Commencez par mesurer cet effet avant de régler une stratégie.",
    example: "Vérifiez le nombre de marchés, les données manquantes et les résultats par période. « Indéterminé » signifie que les preuves ne suffisent pas." },
  { title: "3. Comparer les agents", view: "experiments", action: "Voir les comparaisons",
    text: "Un agent applique une règle de prévision et de décision. Dans Expériences, ouvrez un résultat enregistré ou choisissez des agents pour une nouvelle simulation. Chacun reçoit le même capital initial.",
    example: "Le graphique de rendement part du capital initial : +2 % signifie +20 pour un capital de 1000. La ligne sans transaction sert de repère." },
  { title: "4. Comprendre les pertes", view: "experiments", action: "Lire un résultat",
    text: "Le résultat net inclut les frais simulés. Le repli depuis un sommet, ou drawdown, mesure la baisse du capital par rapport à son meilleur niveau passé. Le Brier mesure l’erreur de prévision : plus petit est meilleur.",
    example: "Un agent peut bien prévoir et perdre de l’argent si son avantage ne couvre pas le prix payé et les coûts. Ouvrez un marché dans le replay pour examiner ses décisions." },
  { title: "5. Découvrir sans se tromper", view: "discovery", action: "Voir les campagnes",
    text: "Découvrir essaie plusieurs règles sur l’entraînement, puis examine les finalistes sur une période ultérieure. Un finaliste est seulement un candidat sélectionné. Le rapport Codex aide à expliquer ses résultats.",
    example: "Modifier une règle après avoir vu sa validation transforme cette validation en donnée de développement. Gardez une nouvelle période intacte pour la vérifier." },
];

export function BeginnerGuide({ navigate }: { navigate: (view: View) => void }) {
  const [open, setOpen] = useState(stored("pmx.guide.v1") !== "done");
  const [step, setStep] = useState(0);
  const lesson = lessons[step];
  const dismiss = () => { setOpen(false); remember("pmx.guide.v1", "done"); };
  return <section className={`panel beginner-guide ${open ? "" : "collapsed"}`} aria-label="Didacticiel débutant">
    <div className="guide-heading"><div><span className="eyebrow">PREMIERS PAS · 3 MINUTES</span><h2>Comprendre avant de lancer</h2></div><button className="button secondary" aria-expanded={open} onClick={() => open ? dismiss() : setOpen(true)}>{open ? "Fermer le guide" : "Ouvrir le guide débutant"}</button></div>
    {open && <>
      <div className="guide-steps" aria-label="Étapes du guide">{lessons.map((item, index) => <button key={item.title} className={step === index ? "selected" : ""} aria-current={step === index ? "step" : undefined} onClick={() => setStep(index)}>{item.title}</button>)}</div>
      <div className="guide-lesson" aria-live="polite"><h3>{lesson.title}</h3><p>{lesson.text}</p><p className="guide-example">{lesson.example}</p></div>
      <div className="guide-actions"><button className="button secondary" onClick={() => navigate(lesson.view)}>{lesson.action} ↓</button><span>{step + 1} / {lessons.length}</span><button className="text-button" disabled={step === 0} onClick={() => setStep(step - 1)}>Précédent</button><button className="button primary" onClick={() => step < lessons.length - 1 ? setStep(step + 1) : dismiss()}>{step < lessons.length - 1 ? "Suivant →" : "Terminer le guide"}</button></div>
      <p className="muted small">Le guide ouvre les écrans ; il ne lance aucun calcul. Vous pouvez le rouvrir à tout moment.</p>
    </>}
  </section>;
}
