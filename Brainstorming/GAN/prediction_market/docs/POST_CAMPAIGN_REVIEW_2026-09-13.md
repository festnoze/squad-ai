# Retour sur la première campagne Polymarket et prochaine priorité

## Diagnostic

La campagne ne démontre aucun avantage exploitable. Elle justifie de modifier l'ordre de recherche,
avant d'augmenter le budget Optuna ou d'introduire un modèle RL. Les hypothèses proposées au moteur
étaient surtout des heuristiques de prix : leur mise en concurrence fonctionne, mais cette compétition
ne crée pas à elle seule une information prédictive.

Preuve primaire : `runs/mvp/campaigns/c-42f3d0040baf469970c83d84/campaign.json`, moteur 2.2.1,
discovery.v1, seed 7, 12 essais, 60 marchés maximum par fold et 1000 USDC par simulation.
Les douze objectifs d'entraînement sont inférieurs à la référence sans transaction. Cet objectif
pénalise le drawdown et l'instabilité : ce n'est pas le PnL brut. Les deux finalistes peuvent donc avoir
un petit PnL d'entraînement positif et rester moins bons que cette référence.

| Mesure | Retournement sur 4 barres | Retournement sur 2 barres |
|---|---:|---:|
| Identifiant | strategy-b7877e19 | strategy-046afa4c |
| Objectif d'entraînement | -18,5833 | -24,5000 |
| Somme des PnL d'entraînement, USDC | +0,95 | +3,75 |
| PnL de validation, USDC | -26,87 | -21,95 |
| Frais de validation, USDC | 5,30 | 4,68 |
| PnL + frais, mêmes exécutions, USDC | -21,57 | -17,27 |
| Marchés effectivement tradés sur les 60 | 37 | 31 |
| Marchés gagnants / perdants / nuls parmi eux | 11 / 26 / 0 | 9 / 21 / 1 |
| Part des cinq pires marchés dans les pertes brutes | 59,3 % | 75,1 % |

Les sommes d'entraînement additionnent des périodes avec capital réinitialisé ; elles ne constituent
pas un rendement de portefeuille continu. Restituer les frais en gardant les transactions constatées
est un calcul comptable, pas un nouveau backtest à frais nuls. Il montre néanmoins que les frais ne
suffisent pas à expliquer les pertes. Le spread simulé reste inclus.

Les moyennes par marché du score de Brier sont aussi légèrement moins bonnes que celles du prix du
marché : environ 0,18201 et 0,18124, contre 0,18020 pour le marché. Ces agrégats ne permettent pas de
conclure à une différence statistiquement significative. La concentration des pertes appelle une
attribution par régime ; elle ne justifie pas d'exclure rétrospectivement les marchés perdants.

La quantité de données utiles est nettement inférieure au nombre de lignes affichées : sur 365980
barres horaires du corpus adapté, seules 29644 comportent du volume observé, soit 8,1 %. Les autres
transportent le dernier prix. Cette mesure concerne le corpus entier, pas un comptage d'événements
indépendants dans la campagne. Le minage initial n'utilisait que 335 observations sur 24 marchés.
Les trois fenêtres d'évaluation interne comportaient respectivement 23, 13 et 5 marchés ; la dernière
est trop petite pour soutenir une généralisation solide.

Le filtre final sur les marchés résolus reste un biais de sélection possible malgré l'échantillonnage
initial indépendant des résultats et la conservation des exclusions. Les liens entre événements,
l'échéance connue à l'époque et les carnets historiques ne sont pas vérifiés. Aucun modèle ne peut
compenser ces informations manquantes simplement en recevant davantage de barres remplies.

## Corrections livrées après ce retour

1. Le minage sur les lignes horaires filtrées utilisait leur indice pour définir une cible « une barre
   plus tard ». Cela pouvait désigner plusieurs heures. Pour les marchés binaires, les cibles de dérive
   utilisent désormais l'horodatage exact ; une observation cible absente n'est pas remplacée par la
   prochaine disponible. Les horizons en barres de séance des actifs continus restent inchangés.
   `discovery.v2` distingue les prochaines campagnes du cache historique. Ce défaut affecte les
   propositions symboliques ; il n'explique pas l'arithmétique des pertes des deux finalistes de prix.
2. L'interface indique explicitement lorsqu'aucun candidat admissible ne dépasse le score du cash.
   Un finaliste est alors présenté comme exploratoire.
3. Une analyse Codex documentée et exportable suit chaque nouvelle campagne terminée lorsque l'option
   est activée. Elle reçoit un dossier chiffré figé, distingue constats et hypothèses et propose au plus
   trois tests. Son échec n'annule pas le backtest. Elle ne lance pas d'expérience et ne réécrit pas les
   résultats. La campagne historique ci-dessus a été soumise explicitement pour cette première revue.

Les compteurs de transactions ont deux sens dans les artefacts existants : les périodes comptent les
quantités exécutées positives ; la projection par marché compte aussi les événements de remplissage
de taille nulle. Le dossier LLM nomme cette différence pour éviter un faux diagnostic comptable.

## Angle d'attaque retenu : mesurer le signal avant d'optimiser la stratégie

La prochaine livraison doit être une **étude de signaux simple sur un corpus plus actif**, avec un
protocole préenregistré et un tableau comparatif dans l'interface. L'objectif est de décider rapidement
si une hypothèse mérite un backtest de stratégie. Les étapes ci-dessous sont proposées, pas exécutées.

### R1 : Données et hypothèses fixées à l'avance

Préparer une tranche ultérieure, par exemple 2024, avec le même importeur vérifiable. Mesurer d'abord
sa densité réelle : une date plus récente n'est pas une preuve de meilleure qualité. Conserver les
marchés censurés dans l'inventaire et quantifier les exclusions. Fixer les dates de développement et
d'évaluation avant de regarder leurs résultats. La validation 2023 déjà inspectée devient une donnée
de développement ; le fold scellé existant reste fermé pendant cette itération.

Limiter l'étude initiale à trois familles. Chaque famille doit avoir une règle précise, des bornes
fixées avant le test et un nombre total de variantes journalisé :

- **Calibration par tranche de prix** : comparer le prix payé à la fréquence de résolution gagnante,
  notamment autour de 90 %. Une réussite de 90 % à un prix de 0,90 ne procure aucun gain attendu avant
  coûts. Pour une unité conservée jusqu'à résolution, l'espérance vaut `q - p - c`, où `q` est la
  probabilité réelle, `p` le prix et `c` les coûts dans la même unité. Choisir à l'avance le point
  d'observation par marché ; mille observations du même contrat ne sont pas mille paris indépendants.
- **Retournement du prix à 24 et 48 heures** : définir mathématiquement le croisement et le mouvement
  qui le précède, puis mesurer la dérive future sur des horizons horaires exacts. Les finalistes actuels
  sur 2 et 4 heures ne constituent pas un test de cette hypothèse. L'espace courant des heuristiques
  couvre 2 à 30 barres : le scénario à deux jours n'a pas été testé comme tel.
- **Activité et fraîcheur du prix** : mesurer les deux familles précédentes sous des conditions
  définies uniquement avec les informations déjà visibles : âge de la dernière transaction et volume
  récent. Les volumes de la fin de vie du marché ne doivent jamais servir à sélectionner une entrée.

Présenter support en marchés, couverture des cibles, effet brut, incertitude et résultat par période.
Les trous de prix doivent être comptés, car conditionner l'analyse à une transaction future peut lui
aussi sélectionner un sous-échantillon. Ne pas interpoler silencieusement une cible absente.

### R2 : Réplication et passage au backtest

Comparer au prix courant pour la prévision et à l'absence de transaction pour le PnL. Utiliser des
blocs temporels et, lorsqu'ils sont vérifiés, des groupes d'événements. En leur absence, déclarer
l'incertitude sur la dépendance. Journaliser tous les essais, contrôler la recherche multiple et
présenter les résultats négatifs avec les positifs. Définir avant exécution un effectif minimum et
un seuil d'effet supérieur aux coûts retenus ; des données insuffisantes donnent « indéterminé ».

Seules les familles reproduites sur plusieurs fenêtres internes passent à une stratégie d'entrée et
de sortie simple. Comparer des scénarios de frais 0/20/50 bp et plusieurs spreads explicitement
hypothétiques. Contraindre la rotation et la durée de détention, puis mesurer le coût d'immobilisation
du capital pour les paris conservés jusqu'à résolution. Ne pas ajuster les frictions pour obtenir du
vert. Geler la règle avant la nouvelle période d'évaluation qui n'a pas servi à sa conception.

### R3 : Un modèle seulement si une information exploitable apparaît

Un petit modèle supervisé régularisé devient alors un candidat utile pour combiner les signaux et
calibrer une probabilité. Il reçoit exactement les mêmes données causales et les mêmes contraintes
d'évaluation que les règles simples. Un modèle RL préentraîné, un LLM décideur ou une migration Forex
ne résolvent pas le manque de signal actuellement observé ; ils ajoutent des degrés de liberté avant
que leur intérêt soit mesuré. L'absence d'effet reproductible est une décision d'arrêt valable.

## Fonctionnement de la revue via l'abonnement

L'application utilise `codex exec` avec la connexion ChatGPT locale vérifiée par `codex login status`.
Elle retire les variables de clé API du processus enfant et impose la connexion ChatGPT. Un compte
connecté uniquement par clé API entraîne une erreur explicite. L'usage consomme les limites de
l'abonnement ; aucun accès illimité n'est supposé.

L'option se règle dans le panneau de campagne. Elle est persistée dans
`runs/mvp/analyses/settings.json`, désactivée par défaut sur une nouvelle installation, et activée sur
cette machine à la demande de l'utilisateur. Les anciennes campagnes ne sont pas analysées en masse.
Une requête identique réutilise le résultat ; une panne ou une interruption demande une relance
manuelle. La reprise traite les travaux en attente et les fins de campagne récentes qui auraient été
manquées au redémarrage. Utiliser un seul processus gestionnaire à la fois pour un même répertoire
de résultats ; ce stockage local n'est pas une file distribuée avec verrouillage interprocessus.

L'analyse a une capacité séparée d'un travail, un délai maximum de 240 secondes pour l'inférence et
20 secondes pour la vérification de connexion. L'API sert le backtest pendant ce temps. La commande
CLI de recherche attend la fin de la revue lorsque celle-ci est activée. Le dossier conservé contient
preuves et empreintes, état, rapport JSON/Markdown et journaux Codex. Le modèle est lancé en lecture
seule, sans configuration MCP personnelle, dans un dossier de tentative ; le prompt interdit les
outils et traite les textes des données comme des observations, jamais comme des instructions.

Ce mécanisme suit les capacités officielles de [connexion ChatGPT de Codex](https://learn.chatgpt.com/docs/auth)
et d'[exécution non interactive avec sortie structurée](https://learn.chatgpt.com/docs/non-interactive-mode).
L'appel réel sur ce poste a vérifié leur fonctionnement avec la connexion existante.

Le premier rapport complet retrouve les constats chiffrés ci-dessus. Ses propositions restent à
arbitrer : par exemple, ajouter des coûts aux deux finalistes déjà perdants renseignerait leur
fragilité, mais ce test apporte moins d'information pour découvrir un signal que R1. Une bonne revue
LLM ne remplace donc ni la vérification des chiffres ni le choix humain des expériences suivantes.
