# REM-23 — lane USD optionnelle, OFF par défaut

Base intégrée f69145fb. Module budget_reservations.py; tracker/config sont raccordés exclusivement par le coordinateur. Aucune activation production revendiquée.

BudgetReservations(cap_usd,journal=external,budget_id,enabled=False,initial_cost_usd=None,historical_unreported=0,producer_root) possède un journal atomique hors source et un verrou inter-processus/threads. Réservation écrite avant retour; enveloppe marquée issued avant dispatch.

ProviderBudgetProof(provider,evidence_path,evidence_sha256) exige un reçu factory revu/hash-pinné : hard USD, logical call entier, tous les coûts facturables, arrêt AVANT overshoot, transport exact active_budget_usd. Ce n'est pas une auto-assertion du provider/modèle; reçu interdit dans le produit. Aucun provider production déclaré compatible. Le flag Claude --max-budget-usd seul ne prouve pas un plafond de facturation; Claude reste sérialisé, option OFF. Token budget actif refusé dans cette lane USD sans transport total-tokens hard-bound.

## API et raccord exact

- acquire(call_id,usd,proof,token_cap=None) -> Reservation. Identité unique; doublon/retry rejeté.
- envelope(reservation) -> ProviderEnvelope, une émission durable. envelope.bind() installe exactement active_budget_usd et restaure le contexte. Second bind/dispatch refusé.
- reconcile(reservation,cumulative_cost_usd,complete=True) garde les totaux connus; receipt répété ne double pas le coût.
- cancel(reservation,cost_usd=None,complete=False) conserve la réserve et bloque si coût inconnu/partiel. Avant dispatch confirmé absent seulement : cancel(cost_usd=0,complete=True).
- update_cap(cap) ne change ni les coûts payés ni les enveloppes admises. Réduction in-flight bloque les prochains appels jusqu'au rapprochement; dette visible.
- snapshot() distingue recorded/reserved/available/debt/overshoot/unreported et raisons de blocage. Restore rend les entrées in-flight unreported, jamais gratuites.

Une seule instance par projet. Activer après rapprochement de TOUS les anciens appels sérialisés. initial_cost_usd est un seed initial audité, pas un compteur estimé recalculé à chaque restore. Restaurer sans remplacer ce seed; divergence cap/historique demande action explicite, pas reset.

Dans _UsageTracker.arun : lane seulement si config ON + preuve compatible; allowance bornée par disponible, pas solde global pour chaque worker. Dans _arun, remplacer active_budget_usd.set(global_remaining) par enveloppe réservée; un bind extérieur serait sinon écrasé. Retour/AgentError : coût provider réellement rapporté, jamais fallback estimé _account. Coût incomplet/annulation devient cancel inconnu; aucune libération sans coût final connu. Observer/checkpoint durable provider reste requis.

Fallback sérialisation seulement pour inéligibilité AVANT admission (OFF, provider non prouvé, token-cap non borné, transport inexact). BUDGET_RESERVED attend; COST_UNREPORTED/STORAGE_FAILED/BOUND_BREACH/CAP_CHANGED bloquent : jamais fallback contournant ledger.

Décimaux/journal conservent petits coûts et overshoots. Si provider viole sa preuve ou cap baisse sous les engagements, rendre l'inégalité vraie en tronquant les faits serait mensonger : dette/breach gardés, aucune nouvelle admission. Panne persistance conserve les derniers faits en mémoire et ferme lane; restore retrouve réservations inconnues bloquantes.

## Preuves offline

pytest tests/test_budget_reservations.py : **15 passed / 5.49s**. Deux processus FakeCLI natifs réellement possédés par Jobs Windows reçoivent chacun --max-budget-usd 0.4 et une barrière prouve leur chevauchement. Troisième réservation0.3 refusée sous cap1; coût final connu0.4/réserve0. Aucun exécutable Claude/API payante lancé. Fake source-revu plafonne son coût; preuve NON transposable au provider production.

Tests : 50 courses/10 enveloppes, receipts incomplets/tardifs/dupliqués, capbaissé, restorecrash, overshoot/conflicting conservés, coût subnormal non disparu, panne disque bloquante, preuve altérée/estimative/token/inexacte refusée. Gain production non mesuré : OFF reste le choix validé. Raccord tracker et contre-revue requis avant fermeture REM-23.
