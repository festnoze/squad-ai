# Gagner un edge sur Polymarket avec des agents IA automatisés (newsfeed + analyse)

> Document de recherche & de raisonnement itératif ("loop thinking").
> Statut : v1.1 — COMPLET. Recherche multi-sources intégrée (§2.1–2.9, dont analyse copy-trading),
> architecture cible (§3), plan de validation (§4), conclusion (§5).
> Date : 2026-06-11

---

## 0. Cadrage

**Question** : comment des agents IA automatisés, branchés sur des flux d'actualité
et des pipelines d'analyse, peuvent-ils obtenir un avantage (arbitrage au sens
strict, ou edge probabiliste) sur Polymarket ?

**Périmètre** :
1. Mécanique de marché Polymarket pertinente pour l'edge (CLOB, frais, oracle UMA, neg-risk)
2. Classes d'arbitrage documentées
3. Edge de latence sur les news
4. Architectures d'agents IA
5. Économie réaliste (spreads, frais, capital, concurrence)
6. Risques et contraintes (ToS, géo, oracle, régulation)

---

## 1. Loop thinking — itérations de raisonnement

(Premiers principes ; les faits vérifiés sont en section 2+.)

### Itération 1 — « l'arbitrage évident existe-t-il encore ? »

Hypothèse naïve : acheter YES + NO < 1$ sur le même marché, profit sans risque.

Raisonnement : si ce free lunch existait durablement, des bots triviaux le
mangeraient. Sur un CLOB liquide, l'écart YES+NO ≠ 1 ne survit que :
- sur les marchés **illiquides** (longue traîne), où la taille capturable est minuscule ;
- pendant des **fenêtres de volatilité** (breaking news) où les market makers
  retirent leurs quotes ;
- sur les structures **multi-outcomes** (somme des YES ≠ 1 sur N candidats),
  plus dures à surveiller — c'est combinatoire, donc moins de concurrents.

→ Conclusion provisoire : l'arb pur existe mais est un jeu d'infrastructure
(vitesse, couverture exhaustive des marchés), pas un jeu d'intelligence.
L'IA n'y apporte presque rien ; un scanner déterministe suffit.

### Itération 2 — « où l'IA apporte-t-elle un edge que la vitesse seule n'apporte pas ? »

Reformulation : l'edge durable = être **mieux calibré** que le marché sur la
probabilité réelle, pas seulement plus rapide.

Trois familles où un LLM/agent a un avantage structurel :
- **Lecture sémantique de la résolution** : les marchés Polymarket se résolvent
  sur des critères textuels précis (règles UMA). Beaucoup de traders parient le
  *titre* du marché, pas sa *règle de résolution*. Un agent qui parse la règle,
  identifie les cas limites (« avant le 30 juin », « selon source X »...) et
  price l'écart titre/règle a un edge réel et peu concurrentiel.
- **Fusion d'information multi-sources** : croiser sondages + données officielles
  + presse locale + réseaux sociaux plus vite et plus largement qu'un humain.
- **Couverture de la longue traîne** : des centaines de marchés à faible volume
  qu'aucun humain sérieux ne suit ; un agent peut tous les pricer en continu.

→ L'IA est un multiplicateur de **largeur** (nombre de marchés couverts) et de
**profondeur de lecture** (règles, contexte), pas de vitesse brute.

### Itération 3 — « le jeu de latence news est-il gagnable ? »

Chaîne de latence : événement → publication source → ingestion → analyse →
décision → ordre on-chain/CLOB → exécution.

Points durs :
- les sources « grand public » (presse) sont déjà en retard sur les insiders
  du domaine (comptes spécialisés, flux officiels, scanners) ;
- un LLM ajoute 1–10 s d'analyse — fatal contre des bots à règles codées en dur
  sur des événements *attendus* (résultats sportifs, chiffres macro, votes) ;
- mais sur les événements *inattendus ou ambigus* (démission surprise, jugement,
  catastrophe), la vitesse pure ne suffit pas : il faut comprendre l'implication
  → fenêtre de quelques minutes où l'analyse LLM bat les deux camps (humains
  trop lents, bots à règles aveugles).

→ Stratégie : ne PAS concourir sur les événements programmés (perdu d'avance
sans infra dédiée) ; cibler les chocs non programmés où le marché met des
minutes à se repricer, et les marchés *corrélés en second ordre* (la news
évidente bouge le marché A instantanément ; le marché B corrélé se reprice
avec retard — c'est là qu'on prend la position).

### Itération 4 — « boucle économique : l'edge survit-il aux coûts ? »

Comptabilité d'un trade : edge brut − spread − slippage − frais (gas/penny) −
coût d'inventaire (capital bloqué jusqu'à résolution) − risque oracle.

Conséquences :
- les micro-edges (<2–3 pts de proba) sur petits marchés sont mangés par le
  spread ; il faut soit des edges gros (chocs news), soit du volume (market
  making informé) ;
- le capital bloqué jusqu'à résolution rend le rendement *annualisé* sensible à
  l'horizon : un edge de 4 pts sur un marché résolu dans 9 mois est pire qu'un
  edge de 1,5 pt résolu demain ;
- le market making assisté par modèle (quotes serrées sur des marchés que
  l'agent sait pricer) transforme l'edge de calibration en flux régulier — mais
  expose à l'adverse selection exactement sur les chocs news qu'on veut chasser
  ailleurs. Les deux stratégies sont complémentaires : le module news sert aussi
  de *circuit breaker* pour le module market making (retirer les quotes quand
  une news tombe).

### Itération 5 — « risques de queue qui tuent le système »

- **Résolution UMA contestée** : un « arbitrage sûr » ne l'est que si la
  résolution est mécanique. Les marchés à règle ambiguë portent un risque
  d'oracle non diversifiable → filtre dur : score d'ambiguïté de la règle, et
  exclusion au-dessus d'un seuil.
- **ToS / géo-restrictions** : l'accès et l'automatisation dépendent de la
  juridiction ; à traiter comme contrainte de conformité de premier ordre, pas
  comme détail.
- **Décay de l'edge** : tout edge publié/observable se fait copier ; le système
  doit mesurer son propre alpha par stratégie et couper ce qui ne paie plus
  (méta-boucle d'allocation).

### Itération 6 — « le flux des autres traders est lui-même un signal »

Particularité unique de Polymarket vs un marché classique : **tout le flux est
on-chain et pseudonyme mais public**. Chaque wallet, chaque fill, chaque
position est lisible. Donc :

- un **insider** qui trade laisse une empreinte : wallet neuf (ou dormant),
  financé récemment, qui prend une position directionnelle agressive et
  démesurée sur UN marché obscur, souvent peu avant l'événement. C'est un
  pattern détectable algorithmiquement (fraîcheur du wallet × concentration ×
  agressivité × obscurité du marché) ;
- inversement, les **smart wallets** (PnL historique élevé, calibration
  démontrée sur N marchés) sont identifiables et suivables — le « copy-trading
  pondéré par la crédibilité » est une stratégie en soi ;
- le détecteur d'insiders a un double usage **offensif** (suivre le flux
  informé = acheter de l'information que quelqu'un d'autre a payée) et
  **défensif** (le module market making retire ses quotes quand un flux toxique
  arrive — c'est de l'anti-adverse-selection).

Limites à vérifier en recherche : taux de faux positifs (les degens riches
ressemblent à des insiders), latence d'indexation des données on-chain,
légalité/éthique du suivi (a priori : données publiques), et le fait que les
insiders sophistiqués fragmentent leurs wallets (→ clustering par source de
financement nécessaire).

### Synthèse du loop thinking (avant intégration des sources)

| Stratégie | Edge | Rôle de l'IA | Concurrence | Verdict |
|---|---|---|---|---|
| Arb YES+NO / neg-risk | structurel, petit | faible (scanner) | bots infra | opportuniste seulement |
| Latence news programmée | vitesse | négatif (trop lent) | très forte | éviter |
| Chocs news non programmés + 2nd ordre | compréhension | fort | moyenne | **cœur du système** |
| Lecture des règles de résolution | sémantique | fort | faible | **edge le plus défendable** |
| Longue traîne mal pricée | largeur | fort | faible | bon complément |
| Market making informé | flux | moyen | forte sur gros marchés | sur marchés moyens, avec circuit breaker news |
| Détection de flux informé / insiders (on-chain) | information d'autrui | fort (pattern + contexte) | faible-moyenne | **signal offensif + défensif** |
| Copy-trading pondéré des smart wallets | calibration d'autrui | moyen (scoring) | moyenne | complément passif |

---

## 2. Recherche vérifiée (multi-sources)

> Résultats consolidés de la recherche parallèle multi-agents (juin 2026).
> Chaque claim porte un niveau de confiance : HAUTE / MOYENNE / FAIBLE.

### 2.1 Mécanique Polymarket (CLOB, frais, oracle UMA, neg-risk)

#### a) Architecture CLOB hybride

- **Matching off-chain, règlement on-chain** : le CLOB de Polymarket est « hybride-décentralisé » — un opérateur centralisé apparie les ordres hors chaîne, puis soumet les trades appariés au contrat **CTF Exchange** sur Polygon, qui vérifie les signatures EIP-712 des deux ordres (prix, taille, allowance) et exécute un swap atomique USDC ↔ tokens d'outcome. Placement/annulation d'ordre sont instantanés et gratuits ; seul le règlement est on-chain. [docs.polymarket.com](https://docs.polymarket.com/trading/overview), [github.com/Polymarket/ctf-exchange](https://github.com/Polymarket/ctf-exchange) — HAUTE.
- **Tokens d'outcome** : ERC-1155 du Gnosis **Conditional Tokens Framework (CTF)** ; chaque paire YES/NO est adossée à exactement 1 USDC.e (désormais « pUSD ») verrouillé dans le contrat CTF. Le contrat Exchange a été audité par ChainSecurity. [chainstack.com](https://chainstack.com/polymarket-api-for-developers/) — HAUTE.
- **Primitives split/merge/redeem** : `split` transforme 1 USDC en 1 YES + 1 NO ; `merge` fait l'inverse (YES + NO → 1 USDC, à tout moment) ; `redeem` convertit le token gagnant en 1 USDC après résolution. C'est la base mécanique de tout arbitrage intra-marché. [docs.polymarket.com](https://docs.polymarket.com/developers/CLOB/orders/orders) — HAUTE.
- **Types d'ordres et microstructure** : ordres limites (GTC/GTD) et ordres « market » (FOK/FAK). Tick sizes par marché : 0,1 / 0,01 / 0,001 / 0,0001 $, avec changement dynamique de tick quand le prix dépasse 0,96 $ ou passe sous 0,04 $ ; un ordre non conforme au tick est rejeté. Taille minimale d'ordre spécifique à chaque marché (exposée via l'API CLOB). — HAUTE.
- **Gas et relayer** : modèle « gasless » : l'utilisateur signe localement, un **Relayer** (type Gas Station Network) diffuse les transactions via des proxy wallets et paie le gas Polygon (déploiement de wallet, approvals, split/merge/redeem, ordres). Le gas est un coût opérationnel de Polymarket, pas de l'utilisateur. [docs.polymarket.com/trading/gasless](https://docs.polymarket.com/trading/gasless) — HAUTE.
- Un **CLOB v2** a été déployé fin avril 2026, accompagné d'un programme de récompenses de liquidité de 1 M$. [crypto.news](https://crypto.news/polymarket-rolls-out-clob-v2-with-1m-liquidity-rewards-to-harden-prediction-markets/) — MOYENNE (presse crypto, peu de détails techniques publics).

#### b) Frais (état 2026 — changement majeur)

- Historiquement **0 % de frais de trading** (2020–2025), modèle subventionné pour la croissance. Fin 2025/début 2026, la plateforme internationale a brièvement appliqué un prélèvement de **2 % sur les gains nets** au règlement, selon plusieurs sources secondaires. [kucoin.com](https://www.kucoin.com/blog/polymarket-fees-trading-guide-2026), [marketmath.io](https://marketmath.io/blog/polymarket-fees-explained) — MOYENNE (non confirmé par une page officielle archivée).
- **Janvier 2026** : premiers taker fees sur les marchés crypto court-terme (5 min/15 min/horaire), avec rebates makers ; extension aux sports le 18 février 2026. [newspoly.net](https://www.newspoly.net/blog/polymarket-fees-guide) — MOYENNE.
- **Barème actuel (« Fee Structure V2 », effectif fin mars 2026)** : frais **taker uniquement**, formule `fee = C × feeRate × p × (1−p)` (maximum à p = 0,50, tendant vers 0 aux extrêmes). FeeRate par catégorie : crypto 0,07 ; sports 0,03 (frais effectif max ~0,75 % à 50/50) ; finance/politique/mentions/tech 0,04 ; économie/culture/météo 0,05 ; **géopolitique et événements mondiaux : 0 %**. Les makers ne paient rien et reçoivent des rebates quotidiens en USDC (20–25 % des taker fees collectés). Les ordres de vente ne paient pas de taker fee. Pas de frais de dépôt/retrait pUSD. [help.polymarket.com](https://help.polymarket.com/en/articles/13364478-trading-fees), [docs.polymarket.com](https://docs.polymarket.com/polymarket-learn/trading/fees) — HAUTE.

→ **Implication stratégique directe** : le régime de frais 2026 favorise structurellement les stratégies **maker** (0 frais + rebates) et pénalise les stratégies **taker** haute fréquence ; la géopolitique (0 %) est la catégorie la moins chère à trader en taker — exactement la catégorie des « chocs non programmés » identifiée en section 1.

#### c) Résolution par l'oracle UMA

- **Mécanisme optimiste** : n'importe qui peut proposer un résultat en postant un bond de **750 pUSD** ; fenêtre de contestation de **2 h** ; si contesté, contre-bond équivalent, et si une seconde proposition est aussi disputée, escalade vers le **DVM** d'UMA (vote des détenteurs de tokens UMA, ~48 h). Résolution totale : ~2 h sans dispute, 4–6 jours avec. Le proposeur gagnant récupère son bond + la moitié du bond adverse. [docs.polymarket.com/concepts/resolution](https://docs.polymarket.com/concepts/resolution) — HAUTE.
- **Controverse « Ukraine mineral deal » (mars 2025)** : le marché « Ukraine agrees to mineral deal before April? » a résolu YES alors qu'aucun accord n'était signé ; une whale UMA a voté avec ~5 M de tokens répartis sur 3 comptes (~25 % des votes du round), ~7 M$ payés sur une résolution fausse ; Polymarket a refusé tout remboursement (« not a market failure »). [thedefiant.io](https://thedefiant.io/news/defi/polymarket-s-usd7m-ukraine-mineral-deal-debacle-traced-to-oracle-whale), [coindesk.com](https://www.coindesk.com/markets/2025/03/27/polymarket-uma-communities-lock-horns-after-usd7m-ukraine-bet-resolves) — HAUTE.
- **Controverse « Zelensky suit » (juillet 2025)** : marché de 160–237 M$ résolu **NO** malgré l'apparition au sommet de l'OTAN décrite comme « costume » par de nombreux médias ; accusations de conflit d'intérêts (vote pondéré par tokens, gros porteurs positionnés NO). [coindesk.com](https://www.coindesk.com/markets/2025/07/07/polymarket-embroiled-in-usd160m-controversy-over-whether-zelensky-wore-a-suit-at-nato), [decrypt.co](https://decrypt.co/329210/polymarket-rules-no-237m-bet-zelenskyys) — HAUTE.
- En réponse, UMA a déployé un oracle « managé » (**Managed Optimistic Oracle V2**, ~août 2025) réduisant le pouvoir des votes bruts sur les cas litigieux. [orochi.network](https://orochi.network/blog/oracle-manipulation-in-polymarket-2025) — MOYENNE. **Implication pour tout bot : le risque de résolution est non négligeable, même à 99 ¢.**

#### d) Marchés « negative risk » (multi-issues)

- Pour les événements à issues mutuellement exclusives (ex. élection à N candidats), le **NegRiskAdapter** (audité ChainSecurity, avril 2024) relie N marchés binaires : l'opération **convert** brûle 1 NO dans un marché et crédite 1 YES dans chacun des N−1 autres (+ du collatéral le cas échéant) ; détenir les N NO (« complement set ») équivaut à du cash. Cela force la cohérence Σ(YES) ≈ 1 et améliore l'efficacité du capital. [github.com/Polymarket/neg-risk-ctf-adapter](https://github.com/Polymarket/neg-risk-ctf-adapter), [docs.polymarket.com/advanced/neg-risk](https://docs.polymarket.com/advanced/neg-risk) — HAUTE.

#### e) Retour aux États-Unis : deux venues parallèles

- Polymarket a racheté **QCEX** (bourse + chambre de compensation licenciées CFTC) pour **112 M$** le 21 juillet 2025 ; feu vert CFTC en septembre 2025 ; **Amended Order of Designation** le 25 novembre 2025 (accès intermédié brokers/FCM) ; relance US effective début décembre 2025. Volume ~7 Md$/mois en février 2026, ~80 % sports. [prnewswire.com](https://www.prnewswire.com/news-releases/polymarket-acquires-cftc-licensed-exchange-and-clearinghouse-qcex-for-112-million-302509626.html), [coindesk.com](https://www.coindesk.com/policy/2025/09/03/u-s-cftc-gives-go-ahead-for-polymarket-s-new-exchange-qcx) — HAUTE.
- Il existe donc **deux venues parallèles** : Polymarket US (régulé CFTC, USD, KYC) et Polymarket international (crypto-natif, Polygon, barème V2). Les deux carnets ne sont pas fongibles : **c'est en soi une source potentielle d'écarts de prix.** — HAUTE (existence) / MOYENNE (exploitabilité).

### 2.2 Classes d'arbitrage documentées

#### Référence académique principale : « Unravelling the Probabilistic Forest » (arXiv 2508.03474, AFT 2025)

- Étude de Saguillo, Ghafouri, Kiffer & Suarez-Tangil sur les marchés résolus entre **avril 2024 et avril 2025** : 8 659 marchés mono-condition + 1 578 marchés neg-risk (17 218 conditions), ~86 M d'ordres on-chain analysés. Profit d'arbitrage réalisé estimé : **39,6 M$**. [arxiv.org/abs/2508.03474](https://arxiv.org/abs/2508.03474) — HAUTE.
- Décomposition : mono-condition **~10,6 M$** (achats YES+NO < 1 $ : 5,9 M$ ; ventes YES+NO > 1 $ : 4,7 M$) ; **neg-risk ~29 M$** (achat de tous les YES < 1 $ : 11,1 M$ ; achat de tous les NO < N−1 : 17,3 M$) ; arbitrage **combinatoire : seulement ~95 K$** (4 paires exploitées sur ~13 identifiées). [collective.flashbots.net](https://collective.flashbots.net/t/arbitrage-in-prediction-markets-strategies-impact-and-open-questions/5198) — HAUTE.
- **Concentration** : le premier arbitragiste a extrait **2,01 M$** en 4 049 transactions ; le top 10 des adresses capte **8,18 M$**. Patterns clairement automatisés chez les top performers. — HAUTE.
- **Réserve méthodologique** : ces chiffres sont des **bornes supérieures** (hypothèse de détention jusqu'à résolution, pas de coût d'opportunité ni de contrainte de liquidité). — HAUTE.

#### Classe 1 — Arbitrage mono-marché (YES + NO ≠ 1 $)

- Acheter YES et NO quand leur somme < 1 $, puis `merge` ou tenir jusqu'à résolution (symétriquement `split` + vendre quand la somme > 1 $). ~10,6 M$ extraits sur avril 2024–avril 2025 — HAUTE. Les écarts apparaissent surtout lors de chocs d'information (débats, résultats sportifs en direct) quand un côté du book se vide plus vite que l'autre. — MOYENNE.

#### Classe 2 — Arbitrage multi-issues / neg-risk (Σ YES ≠ 1)

- Si la somme des YES de tous les candidats < 1 $, acheter tous les YES garantit 1 $ à la résolution ; si la somme des NO < N−1, acheter tous les NO et utiliser `convert` via le NegRiskAdapter. **La classe la plus lucrative historiquement (~29 M$)**, dopée par l'élection US 2024. — HAUTE.

#### Classe 3 — Arbitrage combinatoire (marchés logiquement liés)

- Exploiter des implications logiques entre marchés distincts (ex. « gagnant de l'élection » vs « marge de victoire ») : 13 paires dépendantes identifiées pendant l'élection 2024, mais **très peu exploitées (~95 K$)** — la détection automatique des dépendances logiques reste le verrou. — HAUTE. **C'est la classe où il reste théoriquement le plus d'inefficiences** (et où un LLM a un avantage : comprendre les liens logiques est sémantique, pas numérique), mais aussi celle où le « risque de modèle » (lien logique imparfait) est le plus élevé. — MOYENNE (interprétation).

#### Classe 4 — Arbitrage cross-platform (Polymarket vs Kalshi vs Betfair)

- Acheter YES sur une plateforme et NO sur l'autre quand YES_A + NO_B < 1 $. Spreads documentés de **1,5–4,5 %** sur événements liquides, divergence > 5 points ~15–20 % du temps selon des trackers commerciaux — FAIBLE (sources promotionnelles). Outils open source : [github.com/ImMike/polymarket-arbitrage](https://github.com/ImMike/polymarket-arbitrage) — MOYENNE.
- Coûts : taker fees Kalshi (~1,2 % en moyenne, formule 0,07×p×(1−p)) + désormais taker fees Polymarket : spread brut nécessaire ~1,75–2,5 ¢ par contrat. [polycopy.app](https://polycopy.app/polymarket-kalshi-arbitrage) — MOYENNE.
- **Risque clé : divergence de résolution.** Exemple documenté : marché « Cardi B au Super Bowl » résolu différemment entre Kalshi et Polymarket (critères différents), transformant un arb « sans risque » en perte sur les deux jambes. [defirate.com](https://defirate.com/prediction-markets/how-contracts-settle/) — MOYENNE.

#### Classe 5 — Arbitrage de fin de partie (« endgame », 95–99 ¢)

- Acheter des issues quasi certaines à 0,95–0,99 $ entre l'événement réel et la résolution officielle ; rendements annualisés revendiqués de 15–40 % avec rotation rapide — FAIBLE (estimations praticiennes non auditées). **Ce n'est pas un arbitrage sans risque** : cf. Zelensky suit, où des positions à ~99 ¢ sont allées à 0. — HAUTE (par déduction des cas §2.1c).

#### État de la concurrence en 2026 : fenêtre largement refermée

- Étude UCLA sur les marchés NBA (arXiv 2605.00864, avril 2026) : sur **75 M+ de snapshots de carnet, 173 matchs**, seulement **7 épisodes d'arb mono-marché exécutables** (durée médiane 3,6 s, profit total plafonné à 210 $) ; 290 épisodes combinatoires à ~101 bps médians, mais profondeur exécutable de ~15 shares dans 77 % des cas. Conclusion : « efficience microstructurelle profonde », l'extraction sans risque est confinée à l'**échelle retail** par la faible profondeur des books. [arxiv.org/html/2605.00864v1](https://arxiv.org/html/2605.00864v1) — HAUTE.
- Cas documenté de **latency arbitrage** : un bot a extrait ~271 500 $ en 30 jours en exploitant le décalage entre prix UI et prix on-chain. [predik.io](https://predik.io/en/blog/bot-trading-polymarket-exploit-latencia-arbitraje-en) — MOYENNE.
- **Synthèse sceptique** : les classes 1 et 2 sont aujourd'hui dominées par des bots colocalisés (exécution < 100 ms) et les taker fees 2026 rognent les marges résiduelles ; les poches restantes plausibles sont l'**arb combinatoire** (détection sémantique non triviale — rôle pour l'IA), le **cross-platform avec gestion explicite du risque de résolution**, et l'**endgame** — toutes avec un risque non nul et une capacité limitée. — MOYENNE (synthèse).

### 2.3 Latence news & bots existants

#### a) Vitesse de repricing documentée

- **Étude académique de référence (Kalshi, NBA)** : *« When Do Markets Fully Process Public Information? »* (arXiv 2606.07811, juin 2026) — 1 438 matchs NBA, ~409 500 observations contrat-minute (avril 2025 → mai 2026). Résultat central : une variation d'1 min de la probabilité « benchmark » ne se traduit que par **~0,64-pour-1** dans le midpoint Kalshi — sous-réaction systématique à l'information publique. [arxiv.org](https://arxiv.org/html/2606.07811) — HAUTE.
- **Drift prévisible mais non exploitable (en taker)** : le gap de sous-réaction prédit un drift de **+4,6 pts à horizon 5 min** (coefficients 0,38–0,49, significatifs), MAIS les rendements exécutables **après spread bid-ask sont négatifs** : les coûts absorbent l'anomalie. — HAUTE. **Nuance clé pour nous** : l'anomalie n'est pas exploitable en *prenant* le spread, mais elle peut l'être en le *fournissant* (quotes maker asymétriques orientées dans le sens du drift).
- **Aucune réplication publiée sur Polymarket** : l'extrapolation 0,64-pour-1 à Polymarket reste une hypothèse. — FAIBLE (absence de preuve).
- **Mouvements violents** : sur breaking news majeure, les prix peuvent bouger de **40–50 points en quelques secondes**, forçant les market makers à des retraits de cotation automatisés. — MOYENNE.

#### b) Bots à réaction rapide et leur infrastructure

- **Bots sportifs** : Polymarket expose un **WebSocket sports officiel** (`wss://sports-api.polymarket.com/ws`) diffusant scores et statuts en temps réel. [docs.polymarket.com](https://docs.polymarket.com/developers/sports-websocket/overview) — HAUTE. Le flux WSS du CLOB (~100 ms) bat largement le polling Gamma (~1 s) ; le CLOB tourne sur **AWS eu-west-2 (Londres)**. [tradingvps.io](https://tradingvps.io/measuring-real-trading-execution-latency-on-polymarket/) — MOYENNE.
- **Avantage data sportive** : les flux type Sportradar arrivent jusqu'à **~8 s avant le signal TV** ; tennis et NBA sont les plus sensibles à la latence. — MOYENNE. → Confirmer l'itération 3 : sur les événements *programmés*, la course est perdue d'avance sans data feed payant.
- **Bots macro (CPI/Fed)** : des bots combinent Cleveland Fed Nowcast, FRED, sous-composantes BLS comme signaux. — MOYENNE (architecture plausible, performances non vérifiées).
- **Bots politiques / Truth Social** : services d'alerte (TrumpBot, SentryDock) revendiquant une notification **<30 s** après un post de Trump. [sentrydock.com](https://www.sentrydock.com/sources/truth-social) — MOYENNE. Cas Reuters : avant l'annonce de cessez-le-feu du 7 avril 2026, **≥50 comptes** ont acheté YES avant le post ; un wallet créé le matin même a gagné ~200 000 $ — mais cela relève de la fuite d'info, pas de la latence. [investing.com/Reuters](https://www.investing.com/news/stock-market-news/some-trades-ahead-of-trump-policy-moves-raise-questions-4606365) — HAUTE.

#### c) Cas documentés de profits « latence »

- **Frappes sur l'Iran (fév. 2026)** : premier ordre placé **71 min avant** que la nouvelle ne devienne publique (+553 000 $) ; cluster de 6 wallets frais, **989 191 $ de profit net combiné**. [npr.org](https://www.npr.org/2026/03/01/nx-s1-5731568/polymarket-trade-iran-supreme-leader-killing), [theblock.co](https://www.theblock.co/post/391650/fresh-accounts-netted-1-million-on-polymarket-hours-before-us-airstrikes-on-iran-bubblemaps) — HAUTE. À noter : la « fenêtre de 71 min » montre surtout que le marché ne reprice PAS tant que l'info reste privée — c'est un argument pour le détecteur de flux informé (§2.7), pas pour la course de vitesse.
- **Arbitrage de latence oracle (crypto 15 min)** : le flux Chainlink se met à jour en <1 s mais le carnet Polymarket réagirait en ~55 s en moyenne ; backtest revendiquant ~5 000 opportunités/3 semaines, ~60 % win rate. [github.com/JonathanPetersonn/oracle-lag-sniper](https://github.com/JonathanPetersonn/oracle-lag-sniper) — FAIBLE (auto-déclaré). Polymarket a introduit des **frais dynamiques** (jusqu'à ~3,15 % à 50 ¢) sur les marchés crypto court-terme **explicitement pour casser l'arbitrage de latence**. [financemagnates.com](https://www.financemagnates.com/cryptocurrency/polymarket-introduces-dynamic-fees-to-curb-latency-arbitrage-in-short-term-crypto-markets/) — HAUTE. → Les stratégies taker HFT y sont devenues marginales.

#### d) Repricing retardé des marchés corrélés (second ordre)

- **Mécanisme structurel** : les marchés corrélés tradent sur des carnets isolés — les smart contracts ne lient pas nativement les prix de marchés dépendants, d'où des désalignements transitoires récurrents (cf. arb combinatoire §2.2, ~13 paires identifiées dont 4 exploitées). — MOYENNE.
- C'est la confirmation la plus solide que les marchés de second ordre repricent plus lentement que le marché « principal » touché par la news ; **aucune mesure académique précise du délai de propagation n'a toutefois été publiée** — la quantifier nous-mêmes (données WSS enregistrées) est un prérequis du plan de validation (§4). — FAIBLE sur la quantification.

### 2.4 Architectures d'agents & outillage open source

#### a) Stack développeur officielle (état 2026)

- **CLOB API** (`clob.polymarket.com`, REST + WSS) : carnet, placement/annulation, auth par signature de wallet (clés L1/L2). Matching off-chain (quelques ms), règlement on-chain Polygon. [docs.polymarket.com](https://docs.polymarket.com/developers/CLOB/introduction) — HAUTE.
- **WebSocket CLOB, 4 canaux** : `market` (snapshots de carnet, price changes), `user` (fills, annulations), `sports` (scores live), `RTDS` (temps réel, dont prix crypto Chainlink). — HAUTE.
- **Gamma API** (`gamma-api.polymarket.com`, lecture sans auth) : métadonnées marchés/événements, ~60 req/min. — HAUTE.
- **Data API** (`data-api.polymarket.com`, lecture sans auth) : positions, activité et historique des wallets — la base de tous les outils de copy-trading (cf. §2.7). — HAUTE.
- **SDK Python** : [Polymarket/py-clob-client](https://github.com/Polymarket/py-clob-client) (+ py-clob-client-v2 avec le CLOB v2) gère signature et auth. — HAUTE.

#### b) Frameworks d'agents open source notables

- **[Polymarket/agents](https://github.com/Polymarket/agents)** (officiel, MIT) : framework LangChain — Gamma.py (métadonnées), Polymarket.py (exécution), Chroma.py (RAG sur sources de news), modèles Pydantic, CLI. Complété en 2026 par [Polymarket/agent-skills](https://github.com/Polymarket/agent-skills). — HAUTE sur l'existence ; aucune performance officielle revendiquée.
- **[valory-xyz/trader](https://github.com/valory-xyz/trader)** (Olas) : agent de prédiction pour Omen et Polymarket, architecture FSM, service on-chain via multisig Safe. Sa déclinaison grand public **Polystrat** aurait exécuté >4 200 trades/mois. [olas.network](https://olas.network/blog/polystrat-or-open-claw-what-s-better-for-trading-polymarket-on-autopilot) — MOYENNE (chiffres promotionnels).
- **Projets communautaires** : [web3devz/polytrader](https://github.com/web3devz/polytrader) (LangChain + Exa), [itsabhay83/PolyTrade](https://github.com/itsabhay83/PolyTrade) (LangGraph) — HAUTE sur l'existence, FAIBLE sur toute rentabilité revendiquée.
- **Approche quantitative sans LLM** : [djienne/POLYMARKET_UP_DOWN_DERIBIT_STRATEGY](https://github.com/djienne/POLYMARKET_UP_DOWN_DERIBIT_STRATEGY) — probabilité terminale BTC via surface SSVI calibrée sur options Deribit (Breeden-Litzenberger + Monte Carlo), avec backtester (cf. §2.8d). Même auteur : [djienne/Polymarket-bot](https://github.com/djienne/Polymarket-bot) (bi-stratégie, sizing Kelly). — HAUTE (code public), FAIBLE (pas de track record audité).

#### c) Pipelines de forecasting LLM : structure et résultats

- **Pipeline canonique** (retrieval de news → raisonnement → probabilité calibrée → sizing Kelly → exécution) : formalisé par Halawi et al., *« Approaching Human-Level Forecasting with Language Models »* ([arXiv 2402.18563](https://arxiv.org/abs/2402.18563)) — testé sur 914 questions post-cutoff (dont Polymarket), **Brier 0,179** vs ~0,149 pour la foule humaine — proche mais en dessous. — HAUTE.
- **Tournois Metaculus AIB** : au Q2 2025, **les Pro Forecasters battent nettement le top-10 des bots** (head-to-head −20,03, p = 0,00001) ; les meilleurs bot-makers étaient des hobbyistes, devant les startups. [metaculus.com](https://www.metaculus.com/aib/2025/q2/) — HAUTE. Conclusion sceptique : **les LLM ne battent pas encore les bons forecasters humains** ; un agent LLM n'a d'edge que face à des marchés peu liquides, lents, ou mal lus (règles de résolution) — ce qui recoupe exactement les verdicts de la section 1.
- **Cas médiatisé « ilovecircle »** : 2,2 M$ en 60 jours, win rate revendiqué 74 %, scripts Python générés avec Claude — FAIBLE (cas unique, non audité, recyclé par les médias crypto).

#### d) Part des agents IA dans le volume 2026 — à prendre avec précaution

- « >30 % des wallets utilisent des agents IA » (LayerHub) et « 14 des 20 wallets les plus profitables sont des bots » (tweet repris par Finance Magnates) : **non vérifiables indépendamment**. — FAIBLE.
- Donnée la plus solide : les ~40 M$ d'arbitrage extraits en un an (arXiv 2508.03474, méthodologie on-chain) montrent que l'automatisation domine déjà les classes d'arb mécaniques. — HAUTE.

#### e) Coûts d'infrastructure et position officielle

- **Gas Polygon** : ~0,002 $/tx, <0,01 $/trade ; les ordres CLOB sont signés off-chain (gas seulement sur approvals/redemptions, largement relayé par Polymarket). — HAUTE.
- **Latence d'ordre** : matching en quelques ms côté serveur ; la latence réseau domine (VPS proche d'eu-west-2 ; retail typique 10–100 ms). — MOYENNE.
- **Coût LLM par décision** : quelques centimes à quelques dizaines de centimes selon la profondeur du raisonnement (retrieval ~0,005 $/recherche + tokens) ; le framework [Metaculus/forecasting-tools](https://github.com/Metaculus/forecasting-tools) inclut un Monetary Cost Manager. — MOYENNE.
- **Position officielle** : le trading par API est **explicitement permis et encouragé** (« free and permissionless », repo d'agents officiel, **Builder Program** CLOB v2 avec builder codes et récompenses USDC hebdomadaires). [docs.polymarket.com/builders/overview](https://docs.polymarket.com/builders/overview) — HAUTE. Limites : interdiction ToS pour les juridictions restreintes **y compris via API et agents** — HAUTE ; et frais dynamiques anti-latence sur les marchés crypto courts. En clair : **les bots apporteurs de liquidité sont bienvenus, les snipers de latence sont taxés.**

### 2.5 Économie réaliste

#### a) Spreads et profondeur de carnet

- **Structure des carnets** : étude académique (arXiv 2604.24366, avril 2026, 600 marchés, ~30 Md d'événements tick-level) : « prime de spread sur les longshots » (spreads plus larges aux probabilités extrêmes), profondeur quasi uniforme le long du carnet plutôt que concentrée au top-of-book. [arxiv.org](https://arxiv.org/abs/2604.24366) — HAUTE.
- **Liquide vs long tail** : marchés liquides ~1 ¢ de spread, moyens 3–5 ¢, fins 10 ¢+ ; les marchés >30 jours de durée ont une liquidité moyenne ~450 000 $ contre ~10 000 $ pour les <1 jour. — MOYENNE.
- **Marchés morts** : sur ~21 850 marchés actifs, ~63 % ont un volume nul sur 24 h ; 156 000 contrats de long tail = 7,5 % du volume total. — MOYENNE. → La « longue traîne » de l'itération 2 est réelle mais sa **capacité est minuscule** : c'est un edge de calibration, pas de volume.

#### b) Volumes 2025–2026

- **Volume mensuel** : pic ~10,5 Md$ en mars 2026 (international), ~9 Md$ en avril, ~7,1 Md$ en mai (2ᵉ baisse consécutive) ; Polymarket US : 1,26 Md$ (avril) → 1,77 Md$ (mai). [cnbc.com](https://www.cnbc.com/2026/06/10/polymarkets-volume-falls-again-in-may.html) — HAUTE.
- **Concentration thématique** : sports + politique + crypto = 91 % du volume depuis juillet 2024 (Pew Research) ; ~780 000 participants actifs mensuels au pic. [pewresearch.org](https://www.pewresearch.org/short-reads/2026/05/27/trading-volume-on-prediction-markets-has-soared-in-recent-months/) — HAUTE.

#### c) Pile de coûts réelle par trade

- **Frais** (cf. §2.1b pour la formule) : en pratique ~0,75 $/100 parts sur le sport, 1,00 $ politique/finance/tech, 1,25 $ économie/culture/météo, 1,80 $ crypto (à p=0,50) ; géopolitique 0 ; **maker 0**. — HAUTE.
- **Gas** : quasi nul — un bot réel rapporte 1,19 $ de frais+gas sur 95 830 $ de volume. [kacho.io](https://kacho.io/polymarket-arbitrage-real-numbers) — HAUTE.
- **Immobilisation du capital** : le collatéral (pUSD depuis le 28 avril 2026) ne porte **pas d'intérêt** par défaut ; exception : « Holding Rewards » à 4 % annualisé sur une liste restreinte de positions long terme. [help.polymarket.com](https://help.polymarket.com/en/articles/13364459-holding-rewards) — HAUTE. Le coût d'opportunité (~4–5 % sans risque ailleurs) reste un vrai coût sur les marchés lointains — ce qui confirme l'arbitrage horizon/edge de l'itération 4.
- **Slippage** : significatif hors top-marchés ; règlements parfois retardés de plusieurs heures/jours en cas de dispute (capital gelé). — MOYENNE.

#### d) Statistiques de rentabilité — la base rate est brutale

- **~2,4 % des wallets ont gagné >1 000 $** (37 629 / 1 560 857, CrowdIntel) ; analyse on-chain de 2,5 M wallets : 84,1 % perdants, ~8 000 wallets >10 000 $, 840 wallets (0,033 %) >100 000 $. [crowdintel.xyz](https://crowdintel.xyz/blog/only-2-percent-of-polymarket-traders-made-1000), [coindesk.com](https://www.coindesk.com/markets/2026/04/29/a-tiny-group-is-winning-on-polymarket-as-under-1-of-wallets-take-half-the-profits) — HAUTE. (Affine le ~0,51 % cité en §2.8f.)
- **Concentration extrême** : le top 0,1 % (~1 560 wallets) capte ~71,5 % du ~1 Md$ de profits totaux. [thedefiant.io](https://thedefiant.io/news/research-and-opinion/polymarket-profitability-report-april-2026) — HAUTE.
- **Top traders** : meilleur PnL all-time ~11,8 M$ ; plusieurs comptes à 3,7–4,4 M$ sur ~12–14 M$ de volume. — MOYENNE (leaderboards publics).

#### e) Économie du market making

- **Liquidity Rewards** : paiement quotidien (minuit UTC) pour ordres limites des deux côtés près du mid, scoring quadratique par minute ; **>5 M$ distribués pour le seul mois d'avril 2026** (sports/esports). [docs.polymarket.com](https://docs.polymarket.com/market-makers/liquidity-rewards) — HAUTE (montant : MOYENNE).
- **Rebates makers** : 20–25 % des taker fees reversés quotidiennement. — MOYENNE.
- PnL MM documenté : rare et contradictoire (cf. postmortem tezlee §2.8c : net zéro après adverse selection). — FAIBLE.

#### f) Capital requis et concurrence

- **Étude de cas vérifiable (arb esports, jan–mars 2026)** : +4 973 $ sur 3 858 paris / 95 830 $ de volume avec quelques milliers de $ de capital ; +8 293 $ sur les arbs purs, −3 185 $ sur les jambes non couvertes ; **edge effondré de +2 506 $/mois (fév.) à +390 $ (mars)** après l'arrivée de concurrents et des frais. [kacho.io](https://kacho.io/polymarket-arbitrage-real-numbers) — HAUTE (auto-déclaré mais détaillé). → Le « décay de l'edge » de l'itération 5 est mesuré : division par ~6 en un mois.
- **Ordres de grandeur par stratégie** : arb scanning ~2–10 k$ ; news trading ~5–20 k$ ; MM avec rewards ~10–50 k$ ; calibration long-tail ~5–20 k$ très fragmentés. — FAIBLE (estimation par recoupement).
- Le constat qualitatif d'un « terrain de jeu de bots » saturé sur les stratégies mécaniques est largement corroboré. [financemagnates.com](https://www.financemagnates.com/trending/prediction-markets-are-turning-into-a-bot-playground/) — HAUTE.

### 2.6 Risques & cadre réglementaire 2025–2026

#### a) Statut juridique — États-Unis

- **Retour US régulé** : rachat QCEX (licences CFTC DCM/DCO, 112 M$, juillet 2025), feu vert CFTC sept. 2025, Amended Order nov. 2025, lancement Polymarket US déc. 2025 (cf. §2.1e). — HAUTE.
- **Fronde des États sur le sport** : ≥11 États ont envoyé des cease-and-desist ; contre Polymarket : Tennessee, Connecticut (déc. 2025), Illinois (janv. 2026), injonction préliminaire Nevada (janv. 2026), procès de Polymarket contre le Massachusetts (fév. 2026) ; le DOJ a attaqué Connecticut, Arizona et Illinois en avril 2026 pour préemption fédérale. [stateline.org](https://stateline.org/2026/03/06/kalshi-and-polymarket-are-skirting-laws-on-sports-betting-states-say/), [fortune.com](https://fortune.com/2026/04/04/feds-sue-3-states-for-trying-to-bring-kalshi-and-polymarket-under-more-control/) — HAUTE.
- **Jurisprudence Kalshi divergente** : le 3ᵉ circuit a jugé (avril 2026) que le Commodity Exchange Act préempte le droit du New Jersey, tandis qu'un juge fédéral du Nevada a imposé l'arrêt des contrats sportifs ; résolution Cour suprême plausible. — HAUTE.

#### b) France et UE — point bloquant pour l'auteur de ce document

- **France : Polymarket est illégal et géobloqué.** Après les gains de ~80–85 M$ de Théo sur l'élection US 2024, l'ANJ a ouvert une enquête (nov. 2024) et obtenu un géoblocage IP de tous les utilisateurs français (déc. 2024). [theblock.co](https://www.theblock.co/post/327864/polymarket-blocks-french-users-amid-regulatory-scrutiny-over-80-million-trump-election-bet) — HAUTE.
- **Position ANJ réaffirmée en février 2026** : publication officielle qualifiant les marchés prédictifs (Polymarket, Kalshi) de **sites illégaux en France**. [anj.fr](https://anj.fr/plateformes-de-marches-de-prediction-des-sites-illegaux-en-france-qui-peuvent-presenter-des-risques) — HAUTE. **Conséquence pratique : opérer un bot depuis la France suppose de contourner un géoblocage, en violation des ToS, sur un service réputé illégal localement.** — HAUTE (analyse).
- **UE / MiCA** : pas de régime dédié aux event contracts ; appréhension via MiFID II (l'interdiction ESMA des options binaires aux particuliers plane sur la qualification) et MiCA pour le volet crypto (fin du grandfathering CASP juillet 2026 ; le régime d'abus de marché MiCA s'applique aux prediction markets crypto selon l'ESMA). Enforcement national fragmenté : France, Belgique, Pays-Bas, Portugal, Allemagne, Pologne… [nortonrosefulbright.com](https://www.nortonrosefulbright.com/en/knowledge/publications/290d594a/the-eus-approach-to-prediction-markets-and-event-contracts) — MOYENNE.

#### c) ToS, VPN, gel de comptes, surveillance

- L'usage d'un VPN pour contourner le géoblocage viole expressément les ToS (§2.1.4) ; Polymarket bloque depuis 2026 les IP des fournisseurs VPN dans 33 pays restreints, combine analyse comportementale et KYC ciblé, et **peut geler/saisir les fonds** des comptes en infraction — des cas de soldes verrouillés sans recours sont rapportés. [techradar.com](https://www.techradar.com/vpn/vpn-privacy-security/polymarket-blocks-vpns-and-tightens-identity-verification-as-over-30-countries-ban-the-betting-platform) — HAUTE.
- **Surveillance Chainalysis (30 avril 2026)** : solution de « market integrity » on-chain pour détecter l'insider trading et **partager des preuves avec les régulateurs** — la pseudonymité on-chain ne protège plus. [businesswire.com](https://www.businesswire.com/news/home/20260430726176/en/Polymarket-Selects-Chainalysis-to-Deploy-First-of-Its-Kind-On-Chain-Market-Integrity-Solution) — HAUTE.

#### d) Risque oracle (UMA) — quantifié

- **Attaques avérées** : mars 2025, ~25 % du pouvoir de vote UMA a fait résoudre frauduleusement le marché « minerais ukrainiens » (~7 M$) ; en 2025, >30 M$ de marchés affectés par des résolutions contestées (« proof-of-whales »). — HAUTE.
- **Concentration structurelle** : enquête WSJ (mai 2026) — sur la plupart des marchés disputés, >50 % des votes UMA viennent des 10 plus gros wallets ; ~60 % des votants UMA actifs liés à des comptes Polymarket ; ~1 dispute sur 5 comporte un votant financièrement intéressé. — MOYENNE (relayé).
- **Volume de disputes** : >1 150 marchés disputés en 2026 (déjà au-dessus du total 2025) ; dispute notable : « MicroStrategy vend du BTC avant le 31 mai 2026 » (>60 M$) résolue NO à 98,6 % des votes malgré un 8-K mentionnant 32 BTC vendus. [theblock.co](https://www.theblock.co/post/403600/polymarket-upholds-no-outcome-strategy-bitcoin-sale-market) — HAUTE. Réforme MOOV2 : proposeurs whitelistés, −59 % de propositions erronées. — MOYENNE.

#### e) Risque smart contract

- Contrats CTF Exchange audités (ChainSecurity). Mais le 22 mai 2026, ~600–700 k$ drainés via l'**UMA CTF Adapter** — cause : compromission de clé privée d'un wallet opérationnel admin, hors périmètre d'audit ; fonds utilisateurs non touchés. [cryptonews.com](https://cryptonews.com/news/polymarket-520k-smart-contract-exploit-breakdown/) — HAUTE. Leçon : **le périmètre audité ≠ le périmètre déployé.**

#### f) Insider trading — précédent pénal direct pour les bots « copieurs »

- **Avril 2026** : militaire US inculpé pour avoir parié avec du renseignement classifié (opération Maduro) : ~409 881 $ de profit. — HAUTE.
- **Mai 2026, « AlphaRaccoon »** : Michele Spagnuolo, ingénieur Google, inculpé par le SDNY (fraude CEA, wire fraud, blanchiment — jusqu'à 20 ans) pour ~1,2 M$ de profit via des données internes Google ; première action CFTC pour insider trading sur prediction market. [justice.gov](https://www.justice.gov/usao-sdny/pr/google-employee-charged-insider-trading) — HAUTE.
- Implication : **suivre algorithmiquement le flux d'initiés** (copy-trading de wallets suspects) n'est pas l'infraction poursuivie à ce jour, mais le couple DOJ/CFTC + Chainalysis montre que le flux est surveillé et que la frontière pénale se précise — un wallet copié peut être gelé, et la position du copieur avec. — MOYENNE (analyse).

#### g) Garde des fonds et fiscalité (résident français, bref)

- **International** : auto-custody (proxy wallet, collatéral pUSD 1:1 USDC) — pas de risque dépositaire classique, mais risque de gel applicatif (compliance) et risque stablecoin/bridge. — HAUTE. **US** : modèle intermédié FCM, comptes ségrégués — inaccessible depuis la France. — HAUTE.
- **Fiscalité** : pas de régime « prediction markets » ; en pratique régime des actifs numériques (imposition à la cession contre fiat, PFU ~30–31,4 %, crypto-crypto non imposable, **déclaration 3916-bis obligatoire**). Zone grise : requalification possible en gains de jeux (plateforme jugée illégale par l'ANJ) — non documentée ; consulter un fiscaliste. — MOYENNE / FAIBLE (zone grise).

### 2.7 Détection d'insiders / flux informé (on-chain)

#### a) Transparence des données : tout le flux est public

- Chaque trade, fill, position et wallet est lisible on-chain (contrats CTF
  Exchange sur Polygon). ⚠️ Migration v2 le 28/04/2026 : l'ancien subgraph
  Goldsky est déprécié — les pipelines legacy renvoient des données incomplètes.
  [Goldsky docs](https://docs.goldsky.com/chains/polymarket) — confiance HAUTE.
- **Data API** (`data-api.polymarket.com`, lecture sans auth) : `/positions?user=`,
  `/trades` (filtrable par marché, user, côté taker, taille), `/holders?market=`,
  `/leaderboard` — suffisant pour profiler n'importe quel wallet et surveiller
  les gros fills en quasi temps réel (500 lignes/req).
  [docs.polymarket.com](https://docs.polymarket.com/developers/misc-endpoints/data-api-get-positions) — HAUTE.
- **Goldsky v2 datasets** officiels (positions, open interest, fills) — vendus
  explicitement pour construire leaderboards PnL, whale monitors et bots de
  copy-trading. [goldsky.com/blog/polymarket-dataset](https://goldsky.com/blog/polymarket-dataset) — HAUTE.
- **Dune Analytics** : dashboards communautaires forkables (« Polymarket Whale
  Tracker », « Trader Cashflow PnL ») + alertes Dune = whale-feed gratuit. — HAUTE.
- ⚠️ Depuis avril 2026, Polymarket fait de la surveillance insider en interne
  (partenariat **Chainalysis**) : un wallet flaggé peut être gelé/annulé — le
  signal « suivre l'insider » porte donc un risque de contrepartie croissant.
  [cryptobriefing.com](https://cryptobriefing.com/polymarket-insider-trading-detection-tools/) — HAUTE.

#### b) Cas documentés (2024–2026) — et leur signature de détection

| Cas | Date | Gain | Signature détectable |
|---|---|---|---|
| Google « Year in Search » (AlphaRaccoon, 1ʳᵉ inculpation DOJ) | mai 2026 | ~1,2 M$ / 2,7 M$ misés | un seul compte balaie plusieurs marchés Google obscurs à cotes improbables |
| Sergent US — capture de Maduro | avr. 2026 | >400 k$ | financement frais (~35 k$) une semaine avant + 13 trades concentrés pré-événement classifié |
| Frappe Iran (6 wallets frais, ~1,2 M$) | févr. 2026 | ~485 k$ (top wallet) | wallets neufs, YES pas cher, **71 min** avant la frappe ; 80+ comptes suspects |
| Nobel de la paix (Machado) | oct. 2025 | ~90 k$ | compte frais « 6741 », cote 0,08 → 1,00 $ en quelques heures sans catalyseur public |
| OpenAI browser / GPT-5.2 | oct.–déc. 2025 | 7–13 k$ | wallet neuf + 40 k$ directionnel sur marché tech ; flaggé EN DIRECT par Polysights |
| Théo, la « baleine française » (élection 2024) | nov. 2024 | ~85 M$ | 11 wallets clusterisés par source de financement — mais **informé ≠ insider** : sondages « neighbor polling » commandés en privé |

Leçon clé (cas Théo) : les wallets les plus profitables tiennent parfois une
*recherche supérieure légale*, pas une fuite — les deux types de flux sont des
signaux, mais avec des cinétiques différentes.

#### c) Méthodologies de détection (du plus simple au plus robuste)

1. **Fresh-wallet detection** (la signature n°1 de TOUS les cas documentés) :
   wallet sans historique + financé via CEX depuis peu + pari directionnel
   massif sur marché de niche peu liquide + proche de la résolution.
   Implémentations open source : `pselamy/polymarket-insider-tracker`. — HAUTE.
2. **Seuils praticiens** (PolyTrack, heuristiques non validées — MOYENNE) :
   volume 5–10× la baseline en heures pré-annonce ; flux >95 % unilatéral sans
   catalyseur ; entrées 30 min–2 h avant la news ; win rate catégorie >75–80 % ;
   position = 40–60 % du capital du wallet ou 5–10× sa taille habituelle.
3. **Clustering de wallets** : source de financement commune, trades synchronisés
   à quelques minutes, sizing identique/proportionnel, création quasi simultanée
   (c'est ainsi que les 11 comptes de Théo et le cluster Iran ont été liés). — HAUTE.
4. **Screening statistique** : Mitts & Ofir (Harvard Law, mars 2026) — score
   composite (taille relative, profitabilité, timing pré-événement, concentration
   directionnelle) sur 93 000 marchés → ~210 718 paires wallet-marché flaggées,
   win rate 69,9 %, ~143 M$ de profits anormaux. Important : on score des paires
   **wallet × marché**, pas des wallets (un insider n'est informé que sur UN
   événement). Gomez-Cram et al. : 3,14 % de comptes « skilled », 1 950 comptes
   au pattern de cycle de vie insider (wallet frais → un gros pari → retrait).
   Nechepurenko (arXiv 2026) : Information Leakage Score par marché.
   [arxiv.org/abs/2605.02287](https://arxiv.org/abs/2605.02287) — HAUTE.
5. **Toxicité du flux (VPIN adapté)** : le concept (flux taker unilatéral
   soutenu = flux toxique) se transpose au CLOB Polymarket (flag taker dans la
   Data API), mais aucune étude VPIN-sur-Polymarket publiée — prometteur, non
   validé. — MOYENNE.
6. **Profilage smart-money** : leaderboards PnL + win rate conditionnel par
   catégorie (Data API `/leaderboard`, HashDive « Smart Scores »). Gizmodo
   rapporte ~85 % des trades flaggés par Polysights comme profitables → le flux
   flaggé est une source d'alpha exploitable, pas seulement du bruit compliance. — HAUTE.

#### d) Écosystème d'outils existants

- **Plateformes** : Polysights / « Insider Finder » (24 k users, flags temps réel
  sur X), PolyTrack, HashDive (Smart Scores), polymarketanalytics.com (+ bot
  Telegram PolyGun, 1 % de frais).
- **Bots Telegram copy-trading** : PolyGun, PolyCop, PolyBot (0,5–1 % de frais),
  PolyMate (« Radar » whale-flow), PolyTracker, PolyCopy — écosystème de 170+
  outils catalogués ([defiprime.com](https://defiprime.com/definitive-guide-to-the-polymarket-ecosystem)).
- **Repos open source de départ** : `suislanchez/polymarket-insider-detector`
  (p-values, timing, clustering), `pselamy/polymarket-insider-tracker`,
  `warproxxx/poly_data` (bulk data), `harish-garg/Awesome-Polymarket-Tools`.

#### e) Implications pour l'agent

1. Signal composite à plus haute précision (validé par tous les cas 2025-26) :
   **wallet frais + financement CEX récent + pari >10 k$ à cote longshot +
   marché de niche + timing pré-résolution** → copier VITE : le repricing prend
   de quelques minutes à quelques heures (Nobel : 8 ¢ → 1 $ en heures ; Iran :
   71 min de fenêtre).
2. Distinguer **insider** (pattern one-shot, retrait après gain → signal
   déclencheur d'événement) et **skilled** (~3 % des comptes, edge persistant
   multi-marchés → cible de copy-trading long terme).
3. Risque croissant : inculpations DOJ, surveillance Chainalysis, enquête du
   Congrès → un flux flaggé peut être annulé/gelé ; traiter le signal insider
   comme **décroissant et sensible réputationnellement**.
4. Stack data : Data API (temps réel) + Goldsky v2 (firehose) + Dune (backtest
   et recherche de clusters).

### 2.8 Autres sources de stratégies (biais comportementaux, modèles quantitatifs)

#### a) Inefficiences comportementales documentées

1. **Favorite-longshot bias** — l'edge le mieux documenté académiquement.
   Sur Kalshi, les contrats <10 ¢ perdent **>60 %** de la mise en moyenne ;
   rendement moyen tous contrats : **−22 %** après frais (Bürgi, Deng & Whelan).
   Une étude sur 292 M de trades (Kalshi+Polymarket, [arXiv 2602.19520](https://arxiv.org/pdf/2602.19520))
   montre que le biais se concentre sur les **horizons longs** et les **marchés
   politiques** (compressés vers 50 % par sous-confiance) ; les marchés à court
   horizon sont bien calibrés. — HAUTE.
2. **Time-decay / « theta farming »** : acheter le côté quasi certain des
   marchés longs et porter jusqu'à résolution récolte la prime de compression
   vers 50 % (explication structurelle : capital bloqué sans intérêt →
   [arXiv 2602.21091](https://arxiv.org/pdf/2602.21091)). L'edge croît avec
   l'horizon… mais le coût du capital aussi. — HAUTE (existence) / MOYENNE
   (profitabilité nette).
3. **Sous-réaction aux news publiques avec drift exploitable** :
   [arXiv 2606.07811](https://arxiv.org/abs/2606.07811) (juin 2026) — les prix
   in-game Kalshi ne bougent que **~0,64 pour 1** vs un benchmark d'information
   publique, et l'écart prédit le drift futur (coef. 0,38–0,49, significatif).
   → stratégie momentum POST-réaction initiale, distincte de la course de
   latence. — HAUTE (récent, non répliqué).
4. **Biais « overbet YES »** : Bartlett & O'Hara ([SSRN 6615739](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615739)) —
   les traders sur-misent systématiquement YES dans des marchés qui résolvent
   majoritairement NO → biais systématique côté NO sur les marchés retail
   single-name. — HAUTE.
5. **Distorsion par baleine / biais partisan** : oct. 2024, Théo a poussé le prix
   Trump 10–15 pts au-dessus de PredictIt/Kalshi — l'écart cross-platform était
   en soi un signal de fade/arb. — HAUTE.
6. Effets week-end / nombres ronds : **non démontrés** sur les prediction
   markets (lore praticien seulement). — FAIBLE.

#### b) Stratégies cross-market

- Spreads persistants **1–5 %** Kalshi ↔ Polymarket sur événements identiques.
  Causes structurelles : bases d'utilisateurs différentes, frais (Kalshi ~0,7 % ;
  Polymarket Intl 2 % sur gains nets ; Betfair ~5 %), géo-restrictions, frictions
  de capital, et surtout **risque de divergence de résolution** (mêmes événements,
  critères différents → l'« arb sans risque » peut devenir une perte totale). — HAUTE.
- Outils publics : Oddpool, arbcalculator.cc, actor Apify « Polymarket+Kalshi
  Arb Finder ». L'edge résiduel après concurrence des bots : MOYENNE.
- Vs sportsbooks : l'overround Polymarket/Kalshi (~100–100,5 %) vs Pinnacle
  (~102 %) et retail (105–108 %) rend exécutables des edges de modèle marginaux ;
  benchmark = closing line dé-viggée. — HAUTE.
- **~40 M$ de profits d'arb réalisés** mesurés on-chain sur Polymarket
  (Market-Rebalancing + Combinatorial, [arXiv 2508.03474](https://arxiv.org/abs/2508.03474))
  → l'arb intra-plateforme était réel ET est déjà industrialisé. — HAUTE.

#### c) Market making sur Polymarket

- **Liquidity Rewards** : récompenses quotidiennes pour ordres au repos près du
  mid (formule dYdX adaptée, score quadratique en proximité du mid ; coter
  **2 côtés ≈ 3×** les rewards d'un seul côté).
  [docs officiels](https://docs.polymarket.com/developers/market-makers/liquidity-rewards). — HAUTE.
- Postmortem praticien (tezlee) : bot MM cloné → **net zéro** : rewards + spread
  mangés par l'adverse selection (« un move adverse de 30–40 % efface des
  semaines de gains en minutes »), bugs d'inventaire, impossibilité de hedger en
  carnet mince. D'autres rapportent 700–800 $/jour au pic du rewards farming. — HAUTE.
- Bartlett & O'Hara : la toxicité du flux (type VPIN) prédit les pertes des
  makers sur les marchés single-name, MAIS le sur-pari YES retail y subventionne
  les makers (**2× par contrat**). — HAUTE.
- Primitive spécifique Polymarket : **merge YES+NO → 1 $ USDC** on-chain sans
  slippage = outil de gestion d'inventaire du MM. — HAUTE.

#### d) Modèles quantitatifs vs prix de marché

1. **Crypto binaires vs options Deribit** — le trade « modèle » le plus propre :
   les marchés « BTC above X by date » sont des options digitales ; comparer au
   N(d2) extrait de la surface de vol Deribit (SSVI + Breeden-Litzenberger).
   Écarts typiques de quelques points ; implémentation open source avec
   backtester : [djienne/POLYMARKET_UP_DOWN_DERIBIT_STRATEGY](https://github.com/djienne/POLYMARKET_UP_DOWN_DERIBIT_STRATEGY). — HAUTE.
2. **Météo** : ensembles ECMWF/GFS/ICON vs buckets de température ; entrer quand
   proba modèle − prix ≥ 8–15 pts à ≤48 h. ⚠️ la fenêtre de latence post-run
   (GFS 00/06/12/18Z) s'est compressée de 30–60 min (2024) à **5–15 min (2026)**
   sur les villes liquides — l'edge décroît. — MOYENNE-HAUTE.
3. **Sports** : modèles Elo/Poisson vs marchés, rendus exécutables par le faible
   overround (cf. b). — MOYENNE.
4. **Sondages vs marché (politique)** : le trade « fade le marché vers le
   modèle » a PERDU en 2024 (marché Brier 0,185, 6/8 swing states) ; la version
   robuste est le trade d'écart **cross-platform**, pas modèle-vs-marché. — HAUTE
   (faits) / FAIBLE (supériorité des modèles de sondage).

#### e) LLM forecasting vs marchés (calibration)

- Benchmarks Metaculus 2024→2026 : les bots IA ont comblé une grande partie de
  l'écart avec la foule humaine, mais restent **moins bien calibrés** et moins
  discriminants que les pros — or la calibration EST la quantité tradable. — HAUTE.
- « Wisdom of the Silicon Crowd » (Schoenegger et al. 2024) : un **ensemble de
  12 LLMs** est statistiquement indistinguable de la foule humaine → source de
  proba bon marché à comparer au prix. Compétence **dépendante du domaine**
  ([arXiv 2511.18394](https://arxiv.org/pdf/2511.18394)) → déploiement sélectif. — HAUTE.
- Les agents IA seraient déjà une grosse fraction du flux Polymarket (14/20 top
  wallets, >30 % de l'activité selon des posts 2026) ; les PnL spectaculaires
  rapportés sont **promotionnels et non audités**. — FAIBLE (chiffres) /
  MOYENNE (tendance à la domination des bots).

#### f) Réalité de base à garder en tête

- Seuls **~0,51 % des wallets** Polymarket ont jamais réalisé >1 000 $ de profit
  net ([polymarketanalytics.com](https://polymarketanalytics.com/traders)). — MOYENNE.
- « Why 77 % win-rate traders go broke » : vendre des longshots donne un win
  rate élevé avec des pertes de queue catastrophiques → le sizing (Kelly
  fractionné) n'est pas un détail, c'est la condition de survie. — MOYENNE.

### 2.9 Analyse de stratégie : copy-trading par scoring de wallets

> Analyse approfondie (demande spécifique) — s'appuie sur les faits des §2.5d et §2.7,
> les passages non sourcés sont marqués ANALYSE.

#### a) Le fait de départ : une concentration extrême ET observable

Deux propriétés rares coexistent sur Polymarket :

1. **Les profits sont hyper-concentrés** : le top 0,1 % des wallets (~1 560 comptes)
   capte ~71,5 % du ~1 Md$ de profits totaux ; ~2,4 % des wallets seulement ont
   gagné >1 000 $ (§2.5d) — HAUTE.
2. **Tout le flux est public et attribuable** : positions, fills, PnL historique
   de n'importe quel wallet via la Data API, Goldsky v2 et Dune (§2.7a) — HAUTE.

Sur aucun marché financier classique ces deux propriétés ne coexistent : on sait
que Renaissance gagne, mais on ne voit pas ses trades. Ici, on voit *tout*.
D'où la question légitime : pourquoi ne pas simplement copier les meilleurs ?

#### b) Pourquoi le copy-trading naïf ne marche PAS

1. **PnL brut ≠ compétence.** Avec 2,5 M de wallets, le haut du leaderboard
   contient mécaniquement des chanceux : un wallet qui a parié gros sur un
   longshot gagnant a un PnL énorme et un skill nul. Pire, la stratégie inverse
   (vendre des longshots) produit des **win rates de 77 % avant la faillite**
   (§2.8f) — le win rate et le PnL sont les deux pires métriques de sélection.
   — ANALYSE (fondée sur §2.8f, HAUTE).
2. **Le décalage d'exécution mange l'edge.** On copie *après* le fill ; le fill
   du wallet suivi a déjà déplacé le prix, et les autres copieurs arrivent en
   même temps que nous. Cinétiques mesurées : Nobel 8 ¢ → 1 $ en quelques heures,
   Iran 71 min (§2.7b). L'edge copié = edge du wallet − drift depuis son fill −
   frais taker − slippage. — ANALYSE.
3. **Le suivi de whales est déjà commoditisé.** PolyGun, PolyCopy, PolyBot,
   PolyMate… facturent 0,5–1 % pour exactement ça (§2.7d) ; Polysights flagge
   les insiders EN DIRECT sur X (cas OpenAI, §2.7b). Un signal vendu en bot
   Telegram à 1 % de frais est un signal dont l'alpha résiduel est partagé entre
   tous les abonnés. — HAUTE (existence) / ANALYSE (conséquence).
4. **Les wallets sophistiqués se savent observés.** Théo a opéré sur 11 wallets
   clusterisés seulement a posteriori (§2.7b) ; la fragmentation, voire les
   trades-leurres, sont la réponse rationnelle à un écosystème de copieurs.
   — MOYENNE.
5. **Copier un insider = risque juridique et de contrepartie.** Depuis
   Chainalysis (avril 2026) et les inculpations DOJ/CFTC (§2.6f), un wallet
   flaggé peut voir ses trades annulés/gelés — et la position du copieur
   construite sur ce signal reste, elle, exposée au retournement. — MOYENNE.

#### c) La version défendable : un moteur de scoring, pas un suiveur

L'edge ne réside pas dans le *suivi* (commoditisé) mais dans le *scoring* —
séparer statistiquement la compétence de la chance, et la compétence légale de
l'information privilégiée. C'est un problème de stats + clustering où presque
personne n'investit sérieusement (les bots Telegram se contentent du PnL brut).

**Principes du scoring (ANALYSE, à valider en §4) :**

1. **Scorer des paires wallet × catégorie, pas des wallets.** Un wallet fort en
   politique US n'a aucun edge en NBA. C'est le même principe que Mitts & Ofir
   pour les insiders (§2.7c.4) appliqué aux skilled. Le win rate conditionnel
   par catégorie est exposé par la Data API / HashDive (§2.7c.6).
2. **Métrique = excès de rendement à l'entrée, pas PnL.** Pour chaque trade
   historique du wallet : `edge_réalisé = résultat (0/1) − prix payé`. Moyenné
   sur N trades *indépendants*, avec t-stat. Un wallet skillé a un edge moyen
   positif ET significatif ; un chanceux a un gros PnL porté par 1–2 trades.
3. **Shrinkage bayésien vers zéro.** Prior : ~3,14 % des comptes sont skilled
   (Gomez-Cram et al., §2.7c.4) → tout score doit être rétréci vers « pas de
   skill » proportionnellement à la petitesse de l'échantillon. Sans ça, le
   classement est dominé par les petits échantillons extrêmes.
4. **Distinguer les deux cinétiques** (déjà identifié en §2.7e) :
   - **Skilled persistant** (multi-marchés, edge stable) → cible du copy-trading :
     ses thèses sont lentes (recherche supérieure type Théo), le drift post-fill
     est faible, la fenêtre de copie est de plusieurs heures ;
   - **Pattern insider** (wallet frais, one-shot, pré-résolution) → PAS du
     copy-trading : c'est un déclencheur événementiel à fenêtre de minutes,
     traité par le module flux informé, avec les risques §2.6f.
5. **Condition d'« edge restant » à l'entrée.** Ne copier que si
   `prix_actuel ≤ prix_d'entrée_du_wallet + k × edge_estimé` (k ≈ 0,3–0,5).
   Si le marché a déjà répricé, le trade est mort — l'erreur classique du
   copieur est d'acheter le repricing qu'il a lui-même contribué à créer.
6. **Ensemble plutôt que champion.** Suivre un portefeuille de N wallets scorés
   (pondérés par score), avec contrôle de corrélation : si 5 wallets suivis
   prennent la même position, c'est UN pari, pas cinq — plafonner l'exposition
   par marché, pas par wallet.
7. **Décroissance et re-scoring continus.** Le score d'un wallet est recalculé
   à chaque résolution ; un wallet copié massivement perd son edge (ses fills
   répricent plus vite) — le système doit mesurer l'alpha *réalisé par nous* en
   le copiant, pas l'alpha du wallet.

**Preuve d'existence partielle** : ~85 % des trades flaggés par Polysights
seraient profitables (§2.7c.6, Gizmodo) — le flux scoré est une vraie source
d'alpha ; la question ouverte n'est pas « le signal existe-t-il ? » mais
« que reste-t-il après le lag de copie et la concurrence des copieurs ? »
— c'est LA mesure critique de la phase 1 (§4).

#### d) Économie attendue (ordres de grandeur, ANALYSE)

- Edge brut d'un wallet skillé : 3–8 pts par trade (cohérent avec les ~3 % de
  comptes skilled et leurs PnL, §2.7c.4) ;
- Coûts de copie : frais taker 0–1 % (catégorie) + spread 1–5 ¢ + drift de
  copie (inconnu : à mesurer) → l'edge net copié plausible est de **1–3 pts**
  sur les marchés où le repricing est lent (politique long terme, géopolitique,
  long tail) et **~0** sur le sport liquide ;
- Capacité : limitée par la profondeur (long tail ~10 k$ de liquidité, §2.5a)
  → stratégie de **complément** (10–25 % du capital), pas de cœur ;
- Avantage structurel : c'est la stratégie la moins gourmande en infrastructure
  (pas de course de latence, pas de LLM coûteux en continu — un batch de
  scoring quotidien + un listener de fills suffisent).

#### e) Verdict

Revalorisation par rapport à la synthèse §1 (« complément passif ») : le
copy-trading naïf est commoditisé et sans edge, mais le **copy-trading par
scoring de calibration** est l'une des stratégies au meilleur ratio
edge/complexité du système — à condition que (1) le scoring soit
statistiquement honnête (shrinkage, paires wallet×catégorie), (2) la règle
d'edge restant soit respectée, et (3) le pattern insider soit routé vers le
module événementiel et non copié aveuglément. Elle partage 100 % de son
infrastructure de données avec le détecteur de flux informé (§2.7) : les deux
modules sont un seul investissement technique.

---

## 3. Architecture cible du système d'agents

### 3.0 Principes de conception (dérivés des sections 1–2)

1. **Maker-first.** Le régime de frais 2026 (taker payant, maker gratuit +
   rebates + liquidity rewards, §2.1b/§2.5e) impose d'exécuter en ordre limite
   partout où la fenêtre temporelle le permet.
2. **Pas de course de milliseconde.** La course est perdue d'avance (§2.3b) et
   taxée (frais dynamiques anti-latence, §2.3c). Nos fenêtres : la minute
   (2nd ordre, flux informé) et l'heure/jour (règles, calibration, copy).
3. **Filtre d'ambiguïté de résolution partout.** >1 150 marchés disputés en
   2026, des positions à 99 ¢ allées à 0 (§2.1c, §2.6d) → score d'ambiguïté
   obligatoire, position interdite au-dessus du seuil, quel que soit l'edge.
4. **Alpha mesuré par stratégie, kill switch par stratégie.** L'edge se
   divise par 6 en un mois quand la concurrence arrive (§2.5f).
5. **Le module news est aussi une défense.** Retrait des quotes MM < 1 s sur
   choc détecté (anti-adverse-selection, itération 4 + §2.8c).
6. **Conformité d'abord.** Le gate juridique (§2.6b : France = illégal/géobloqué)
   précède tout déploiement réel — voir §4 phase 0.

### 3.1 Vue d'ensemble

```
┌─────────────────────────── INGESTION ───────────────────────────┐
│ WSS CLOB (books, fills)  │ Gamma/Data API  │ Goldsky v2 / Dune  │
│ News (RSS, X, officiels) │ Sports/RTDS WSS │ On-chain watcher   │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌────────────── COMPRÉHENSION (LLM, batch + événementiel) ─────────┐
│ RuleParser : règle UMA → critères, cas limites, score ambiguïté, │
│              écart titre/règle                                   │
│ DependencyGraph : liens logiques entre marchés (1er/2nd ordre)   │
│ NewsClassifier : programmée/choc, marchés impactés, ambiguïté    │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌────────────── PRICING ───────────────────────────────────────────┐
│ FairValue par marché : ensemble LLM (Brier tracké) + modèles     │
│   quant par domaine (N(d2) Deribit crypto, ensembles météo, Elo) │
│ WalletScorer : skill par wallet×catégorie, shrinkage bayésien    │
│ InsiderDetector : signal composite §2.7e (frais+CEX+taille+niche)│
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌────────────── DÉCISION & RISQUE ─────────────────────────────────┐
│ edge_net = |fair − prix| − frais(catégorie, p) − spread/slippage │
│            − coût_capital(horizon)                               │
│ Kelly fractionné (≤ 0,25 Kelly) • caps marché/catégorie/stratégie│
│ Filtres durs : ambiguïté > seuil, liquidité < min, juridiction   │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌────────────── EXÉCUTION ─────────────────────────────────────────┐
│ py-clob-client • maker-first • taker ssi edge_net > seuil_taker  │
│ CircuitBreaker : annulation de toutes les quotes < 1 s sur choc  │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌────────────── MÉTA-BOUCLE ───────────────────────────────────────┐
│ Post-mortem par trade (edge estimé vs réalisé) • Brier par module│
│ Suivi du decay par stratégie • allocation de capital • kill      │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Les sept modules stratégiques

| Module | Fenêtre | Signal | Exécution | Fondement |
|---|---|---|---|---|
| **RuleEdge** (écart titre/règle) | heures–jours | RuleParser : le marché price le titre, pas la règle | maker | §1 it.2, §2.1c |
| **SecondOrder** (chocs non programmés) | 1–30 min | NewsClassifier + DependencyGraph : marché B corrélé pas encore répricé | taker (géopolitique = 0 % de frais) | §1 it.3, §2.3d |
| **LongTail** (calibration) | jours | FairValue vs prix sur marchés sans suiveurs | maker uniquement | §1 it.2, §2.5a |
| **InformedFlow** (insiders) | minutes | InsiderDetector (§2.7e) | taker rapide, taille plafonnée, risque §2.6f | §1 it.6, §2.7 |
| **SmartCopy** (copy scoré) | minutes–heures | fills de wallets à score élevé + règle d'edge restant | maker si possible | §2.9 |
| **InformedMM** (market making) | continu | quotes autour de FairValue, rewards + rebates | maker, retrait sur CircuitBreaker | §1 it.4, §2.8c |
| **ArbScanner** (résiduel) | secondes | YES+NO, Σ neg-risk, cross-platform à règles identiques | taker opportuniste | §2.2 |

Notes :
- **SmartCopy et InformedFlow partagent le même pipeline de données** (Data API
  + Goldsky + clustering de wallets) — un seul investissement technique, deux
  cinétiques de signal (§2.9c.4).
- **ArbScanner n'est pas un centre de profit** (fenêtre refermée, §2.2) : il
  sert de capteur d'anomalies (un arb qui s'ouvre = un choc en cours) et
  ramasse l'opportuniste.
- L'**ordre de construction** suit le ratio edge/complexité : WalletScorer +
  SmartCopy d'abord (données seules, pas de LLM temps réel), puis RuleEdge
  (LLM batch), puis LongTail, puis SecondOrder (news temps réel), puis
  InformedMM (le plus risqué), ArbScanner en tâche de fond.

### 3.3 Choix techniques

- **Python 3.11+, asyncio** (méthodes préfixées `a` selon la convention projet),
  `py-clob-client` pour l'exécution, WSS natifs pour l'ingestion.
- **Event bus interne** (queues asyncio) : chaque module est un consommateur
  indépendant — un module qui crashe ne tue pas les autres ; le CircuitBreaker
  publie sur un topic prioritaire.
- **Persistance** : Parquet pour les flux (ticks, books, fills — réutilise le
  pattern cache du projet trading_agents) ; SQLite/Postgres pour les décisions,
  scores de wallets, post-mortems.
- **LLM budgété** : le RuleParser et le FairValue LLM tournent en batch
  (nouveau marché, nouvelle news, mouvement de prix > seuil), jamais en
  polling — coût cible < 0,2 $/marché/jour (§2.4e).
- **Journal de décision obligatoire** : chaque trade logge prix, fair value,
  edge estimé, frais estimés, module source, raison textuelle → c'est la
  matière première de la méta-boucle et du post-mortem.

---

## 4. Plan de validation incrémental

### Phase 0 — Gate de conformité (BLOQUANT, avant tout le reste)

La recherche (§2.6b) établit que Polymarket est géobloqué et déclaré illégal en
France par l'ANJ, que le contournement par VPN viole les ToS et expose au gel
des fonds (§2.6c). Trois options, à trancher AVANT d'écrire du code d'exécution :

| Option | Légalité | Conséquence |
|---|---|---|
| (a) Recherche & paper trading sur données publiques uniquement | OK (lecture de données publiques) | Le projet reste un projet de recherche ; phases 3-4 gelées |
| (b) Opérer depuis une juridiction autorisée (entité ou résidence) | à valider avec un avocat | Coût/complexité ; fiscalité à structurer (§2.6g) |
| (c) Porter le système sur une venue accessible légalement | dépend de la venue | L'architecture §3 est portable (l'edge sémantique et le scoring de wallets moins : ils dépendent de la transparence on-chain de Polymarket) |

→ Par défaut, ce projet démarre en **option (a)** : tout le plan ci-dessous
jusqu'à la phase 2 incluse est réalisable légalement sans compte de trading.

### Phase 1 — Collecte & replay (4–6 semaines, coût ≈ 0)

Objectif : remplacer les « FAIBLE » de la section 2 par nos propres mesures.

1. Enregistrer en continu : books + fills WSS sur ~200 marchés (mix liquide /
   long tail), news timestampées (RSS + X + flux officiels), flux on-chain
   (Data API + Goldsky).
2. Mesurer ce que personne n'a publié :
   - **délai de propagation 1er → 2nd ordre** (la quantification manquante, §2.3d) ;
   - réplication du **0,64-pour-1** (sous-réaction) sur Polymarket ;
   - **drift post-fill des wallets à haut score** = l'edge restant réel du
     module SmartCopy (la mesure critique de §2.9c).
3. Backtester : WalletScorer sur l'historique Goldsky/Dune (les résolutions
   passées donnent la vérité terrain) ; FairValue LLM sur marchés résolus
   (Brier vs prix de marché à J-7/J-1).
4. **Critère de sortie** : ≥ 2 modules avec edge net simulé > 0 après frais V2,
   spread réel observé et slippage modélisé. Sinon : itérer ou arrêter — c'est
   un résultat aussi.

### Phase 2 — Shadow trading (4–8 semaines, coût ≈ LLM seul)

1. Système complet (§3.1) en temps réel, ordres **simulés** contre le book réel
   enregistré au moment de la décision (fill simulé conservateur : maker fillé
   seulement si le prix traverse, taker au pire du spread).
2. Métriques par module : Brier, calibration (reliability diagram), PnL simulé
   net, demi-vie de l'edge, taux de faux positifs de l'InsiderDetector.
3. **Kill par module** : PnL simulé < 0 après coûts sur la fenêtre → retour en
   phase 1 pour ce module ; les autres continuent.

### Phase 3 — Micro-capital (CONDITIONNEL au gate 0, options b/c)

- 500–2 000 $, tailles minimales, 2–3 modules max (commencer par SmartCopy et
  RuleEdge : fenêtres lentes, moins sensibles à l'exécution).
- Mesurer l'écart shadow vs réel : fill rate maker effectif, slippage réel,
  adverse selection sur nos quotes — **cet écart est le « coût de réalité »**
  qui invalide ou valide tout le backtest.
- Circuit breakers actifs dès le premier jour : perte jour > 5 % du capital →
  arrêt total ; dispute UMA sur une position > 10 % du capital → alerte humaine.

### Phase 4 — Montée en charge

- Allocation de capital par alpha réalisé (méta-boucle), réévaluée chaque
  semaine ; plafond par stratégie et par marché.
- Provision de décroissance : hypothèse par défaut = l'edge de chaque module
  se divise par 2 tous les 2–3 mois (§2.5f) tant que la mesure ne dit pas mieux.

### Métriques permanentes (tous modules, toutes phases)

1. **Brier score** par module et par catégorie, comparé au Brier du prix de
   marché à l'entrée (battre le marché, pas la météo) ;
2. **Edge réalisé vs edge estimé** — calibre le modèle d'edge lui-même ;
3. **Decay** : PnL net par stratégie par mois, avec alerte de tendance ;
4. **Toxicité de notre propre flux** : ratio fills maker / annulations, drift
   du prix après nos fills (sommes-nous le pigeon de quelqu'un ?) ;
5. **Exposition oracle** : capital total sur marchés à score d'ambiguïté moyen,
   plafonné en dur.

---

## 5. Conclusion — verdict actualisé

La recherche (section 2) confirme l'intuition centrale du loop thinking : **la
vitesse est un jeu perdu et taxé ; la compréhension et le scoring sont les
seuls edges accessibles**. Verdicts mis à jour :

| Stratégie | Verdict §1 (a priori) | Verdict final (après recherche) |
|---|---|---|
| Arb YES+NO / neg-risk | opportuniste | **Confirmé en pire** : fenêtre refermée (7 épisodes exécutables sur 173 matchs NBA, §2.2) ; capteur d'anomalies, pas un centre de profit |
| Latence programmée | éviter | **Confirmé** : course perdue + frais dynamiques anti-latence (§2.3c) |
| Chocs non programmés + 2nd ordre | cœur du système | **Renforcé** : géopolitique à 0 % de frais (§2.1b) ; délai de propagation 2nd ordre jamais quantifié publiquement → à mesurer soi-même (avantage au premier qui mesure) |
| Lecture des règles de résolution | edge le plus défendable | **Renforcé mais double tranchant** : >1 150 disputes en 2026 — l'ambiguïté est à la fois l'edge (mal pricée) et le risque (résolution whale, §2.6d) |
| Longue traîne | bon complément | **Tempéré** : réelle mais capacité minuscule (63 % de marchés morts, ~10 k$ de profondeur, §2.5a) |
| Market making informé | sur marchés moyens | **Confirmé avec preuves** : >5 M$/mois de rewards (§2.5e) mais postmortems d'adverse selection brutaux (§2.8c) ; dernier module à construire |
| Flux informé / insiders | signal offensif + défensif | **Tempéré** : le signal marche (85 % des flags profitables) mais surveillance Chainalysis + précédents DOJ → signal décroissant, taille plafonnée (§2.6f) |
| Copy smart wallets | complément passif | **Revalorisé** (§2.9) : naïf = commoditisé et mort ; par scoring de calibration = meilleur ratio edge/complexité du système, premier module à construire |

**Les trois conclusions opérationnelles :**

1. **Le vrai bloquant n'est pas technique, il est juridique** : Polymarket est
   illégal en France (ANJ, §2.6b). Le projet est viable en mode recherche/shadow
   (phases 0–2) ; tout déploiement réel exige de résoudre le gate de conformité.
2. **L'ordre de construction optimal** : WalletScorer + SmartCopy (données
   seules, edge mesurable vite) → RuleEdge (LLM batch) → LongTail → SecondOrder
   (news temps réel) → InformedMM → ArbScanner. Chaque module ne passe en
   production que sur alpha mesuré, jamais sur conviction.
3. **La rente n'existe pas** : l'étude de cas §2.5f (edge ÷6 en un mois) est le
   destin par défaut de toute stratégie ici. Le système n'a de valeur que si la
   méta-boucle (mesure du decay + réallocation + kill) fonctionne — c'est elle,
   pas une stratégie particulière, le véritable actif.
