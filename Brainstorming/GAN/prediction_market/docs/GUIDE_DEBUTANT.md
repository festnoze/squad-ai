# Premiers pas dans l'atelier

Ouvrez l'application sur http://127.0.0.1:8175. Le guide « Comprendre avant de lancer » apparaît lors
de votre première visite. Ses cinq étapes peuvent être lues dans l'ordre ou choisies directement.
« Terminer le guide » mémorise sa fermeture dans ce navigateur. « Ouvrir le guide débutant » permet
de le retrouver. Le guide ne lance jamais de simulation à votre place.

## 1. Explorer un marché

Un contrat OUI coûte un prix compris entre 0 et 1 et verse 1 si l'événement se réalise. À 0,90,
une victoire rapporte 0,10 avant frais et une défaite coûte 0,90. Le taux de réussite ne suffit donc
pas pour choisir une stratégie. Dans Explorer, ouvrez un marché et observez prix, volume et dates.
Les identifiants techniques restent affichés quand la question historique n'est pas vérifiée.

Une heure sans transaction n'est pas une nouvelle information de prix. Consultez la couverture et
les limites du jeu choisi avant d'interpréter ses courbes. Le premier chargement vérifie le corpus
local et peut durer plusieurs minutes ; le guide reste accessible pendant cette vérification.

## 2. Mesurer un signal

Sélectionnez `polyarchive2024h1` dans le jeu actif, puis ouvrez Signaux. Le protocole R1 examine
28 variantes annoncées à l'avance sur l'entraînement, sans ouvrir la validation pour choisir une règle.
Cliquez sur « Exécuter le protocole R1 », ou rouvrez l'étude enregistrée. Une exécution identique
réutilise le même résultat. Les observations et les résultats sont téléchargeables.

Le graphique de calibration compare prix moyen et fréquence gagnante. Au-dessus de la diagonale,
la fréquence dépasse le prix ; cela reste un effet brut observé, avec incertitude et sans simulation
des coûts. Les petits groupes sont signalés par des cercles vides. Choisissez « Actif et prix récent »
pour lire la condition d'activité prédéfinie, puis cliquez sur une hypothèse pour voir ses trois mois.

- **Indéterminé** : support ou couverture insuffisants.
- **Non retenu** : les critères descriptifs annoncés ne sont pas tous satisfaits.
- **À répliquer** : cette observation mérite un nouveau test indépendant, sans preuve de rentabilité.

« pp » signifie point de probabilité : passer de 60 % à 61 % représente +1 pp, soit +100 points de base.
Les cibles absentes restent absentes ; elles ne sont ni interpolées ni comptées comme un résultat nul.

## 3. Comparer des agents

Dans Expériences, commencez par ouvrir un résultat enregistré. Pour une nouvelle comparaison,
choisissez la plateforme, les stratégies, un échantillon limité et le capital par stratégie, puis
lancez le calcul. Chaque stratégie applique une règle explicite ; la référence marché ne passe pas
d'ordre. Une graine identique rend la sélection et la simulation reproductibles.

Le graphique « Comparer les trajectoires » affiche :

- **Rendement net** : écart au capital initial, frais inclus. +2 % représente +20 sur un capital de 1000.
- **Capital** : valeur du portefeuille, positions encore ouvertes comprises.
- **Repli depuis le sommet** : baisse depuis le meilleur capital déjà atteint ; une valeur plus
  négative correspond à une baisse plus importante.

Décochez un agent pour masquer sa courbe. Déplacez le curseur ou cliquez dans le graphique pour
lire les valeurs à une date. Les dates sont en UTC. La ligne sans transaction fournit une référence.
Les montants de différentes devises ne sont pas additionnés.

## 4. Comprendre un résultat

Le Brier mesure l'erreur de prévision : plus bas est meilleur. Le gain de Brier compare l'agent au
prix du marché. Le résultat économique inclut les frais simulés. Une meilleure prévision peut rester
insuffisante pour gagner de l'argent après coûts. Ouvrez le replay d'un marché pour examiner les
positions, les prévisions et les transactions qui ont conduit au résultat.

Dans une expérience, les agents partagent la liquidité simulée. Dans une campagne de découverte,
les finalistes sont évalués séparément. Leur comparaison graphique utilise la même période et les
mêmes marchés de validation ; leurs capitaux ne forment pas un portefeuille commun.

## 5. Découvrir et décider de la suite

Découvrir teste plusieurs règles et paramètres sur l'entraînement avant d'examiner les finalistes
sur une période ultérieure. « Finaliste » décrit une sélection relative, pas une stratégie rentable.
Le bandeau indique lorsqu'aucun candidat ne dépasse l'objectif de la référence sans transaction.

Le rapport Codex propose une lecture des résultats et des tests suivants. Son option automatique
utilise le quota de votre abonnement ChatGPT connecté au Codex local. Les propositions ne sont pas
exécutées automatiquement. Les tableaux et journaux restent les preuves à vérifier.

Après avoir regardé une validation, modifier la stratégie en fonction de ce résultat transforme
cette période en donnée de développement. Il faut alors une nouvelle période intacte pour vérifier
la règle. Un résultat négatif ou indéterminé est une information utile pour arrêter une piste.
