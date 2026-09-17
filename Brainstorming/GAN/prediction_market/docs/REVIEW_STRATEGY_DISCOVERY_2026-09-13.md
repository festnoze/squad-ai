# Modèles Hugging Face et chemin le plus court vers la découverte de stratégies

Analyse du 13 septembre 2026, à partir du [document fourni par l'utilisateur](C:/Users/e.millerioux/Downloads/analyse_modeles_huggingface_trading_rl-3.md), de sources primaires et de l'état réel de pmx. Les prescriptions du document joint sont étudiées comme des propositions ; elles ne sont pas exécutées. Aucun checkpoint n'a été chargé, aucun entraînement ni benchmark de rentabilité lancé.

**Recommandation : conserver le moteur et les données du projet, raccorder le mineur de règles, et utiliser Optuna pour une recherche bornée de paramètres.** C'est le premier chemin que je choisirais pour obtenir un outil qui cherche effectivement des stratégies. Les checkpoints RL examinés ne constituent pas un raccourci démontré. Si un premier modèle appris est ajouté, je privilégierais ensuite un petit LightGBM supervisé, évalué par le même moteur, avant un allocateur SAC.

Ce choix est une recommandation d'ingénierie pour ce dépôt et cet objectif. Il ne prouve pas que les règles ou LightGBM seront plus rentables que le RL. La comparaison empirique reste à faire.

**Ce que le document apporte de juste**

Son constat essentiel est fondé : une politique RL sauvegardée dépend de son environnement. Les colonnes, leur ordre, les transformations, la fréquence, les actions, les coûts et les contraintes font partie du modèle utilisable. Télécharger des poids ne supprime pas ce contrat. Les performances affichées par des auteurs différents ne permettent pas de classer leurs approches si les marchés, les périodes, le risque et les coûts diffèrent.

Je retiens aussi la séparation entre prédiction, décision, exécution et comptabilité ; les contrôles simples ; les expériences à plusieurs seeds ; et la validation chronologique. Ces principes sont largement compatibles avec pmx.

En revanche, la recommandation centrale du document ne découle pas de sa propre inspection. Il constate que les modèles ne sont pas directement réutilisables, puis propose un nouvel allocateur SAC, un environnement, une représentation et un protocole sur huit à douze semaines. C'est un programme de recherche possible, mais il ne répond pas au mieux à la contrainte « développer facilement un outil pour découvrir des stratégies ».

La proposition la plus adaptée à un premier apprenant figure plutôt dans sa section 5.1 : prévoir un résultat avec un modèle supervisé, puis traduire cette prévision en décisions explicites. Elle mérite une priorité supérieure au RL.

**Ce que les vérifications changent dans le classement**

| Candidat | Conclusion utile pour pmx |
|---|---|
| LearnFinance SAC | Inspiration d'allocation continue ; portabilité et avantage hors échantillon non établis |
| ParallelLLC / Afterluck | Méthodes de validation intéressantes ; aucun motif suffisant pour remplacer notre moteur |
| GPy-Trade | Bonne séparation des signaux et de la décision ; pas de validation suffisante dans la fiche pour adopter les poids |
| UG-CPPO | Résultat négatif instructif et défaut confirmé dans l'environnement publié ; éviter son adoption directe |
| Adilbai et petits ensembles DQN/PPO/A2C | Démonstrateurs à considérer individuellement ; les rendements affichés ne constituent pas une preuve réutilisable |

La fiche **LearnFinance SAC** consultée est déjà différente de celle décrite dans le document : elle annonce la version `2026-09-04_e6d032d2`, un entraînement jusqu'au 4 septembre 2026 et un Sharpe de 1,7333. Elle décrit trente slots d'actions et le cash, avec un chargement dépendant de `brain_api`. Je n'ai pas établi de période de test distincte ni de contrat autonome complet. Ce sont des informations publiées, pas des performances reproduites. [Fiche LearnFinance](https://huggingface.co/hajirazin/learnfinance-models-sac-it-heavy).

Pour **UG-CPPO**, la critique du reward est confirmée par lecture du code : `step()` valorise avant et après les transactions avec les mêmes prix, calcule le reward, puis avance la date. Le gain de détention entre deux dates n'entre pas dans cette différence ; les frais dominent donc la récompense immédiate. Cela disqualifie cet environnement comme base directe. Cela ne démontre pas que tous les checkpoints publiés ont été entraînés avec ce fichier exact. [Code de l'environnement](https://github.com/graceesthi/ug_cppo/blob/main/src/ug_cppo_env.py#L122).

La fiche UG-CPPO publie dix seeds et ne démontre pas d'amélioration face à PPO : rendement moyen annoncé de 35,99 %, contre 43,94 %, avec une différence non significative. Ce résultat ne prouve ni équivalence, ni supériorité générale de PPO ; il n'appuie simplement pas l'ajout de complexité comme raccourci. [Résultats du producteur](https://huggingface.co/graceesthi/ug-cppo-finai-2025).

Le dépôt GitHub **ParallelLLC/algorithmic_trading** redirige désormais vers **Afterluck**. Son README décrit permutation, DSR, PBO, walk-forward et stress des coûts. Les implémentations statistiques n'ont pas pu être auditées ici ; leur présence annoncée ne vaut pas validation. Son score synthétique ne doit pas être lu comme une probabilité de rentabilité. Le transfert des permutations aux contrats binaires demanderait aussi de préserver les échéances, les issues complémentaires et les groupes d'événements. [Afterluck](https://github.com/ParallelLLC/afterluck).

**GPy-Trade** combine effectivement PPO, classification de direction, prévision de volatilité et détection d'anomalies. La fiche consultée fournit ces composants mais pas un protocole de test économique suffisamment documenté. Je retiens la séparation conceptuelle des tâches. [Fiche GPy-Trade](https://huggingface.co/maherdik/gpy-trade-model).

**Adilbai** affiche effectivement des drawdowns dépassant 100 % et un exemple de backtest qui n'applique pas les coûts annoncés ailleurs. Une définition inhabituelle, un levier ou une erreur doivent être éclaircis avant toute comparaison ; les chiffres ne sont donc pas une base de choix. [Fiche et exemple publiés](https://huggingface.co/Adilbai/stock-trading-rl-agent).

**Pourquoi le RL n'est pas mon premier choix ici**

Le besoin initial est de découvrir un avantage conditionnel : dans quel contexte le paiement final ou le mouvement futur est-il favorable par rapport au prix et aux coûts ? Le RL peut apprendre une telle décision, mais il couple cette recherche avec le dimensionnement, l'abstention, le calendrier et la gestion du portefeuille. Cela augmente les causes possibles d'échec et rend le diagnostic plus difficile.

L'intérêt du RL devient plus précis quand les décisions successives changent sensiblement les possibilités futures : répartition du capital entre opportunités, inventaire, coûts de changement de position, sorties progressives. Ce problème existe en trading. Il n'est simplement pas nécessaire de le résoudre entièrement pour tester les premiers signaux demandés.

SAC est compatible avec les actions continues ; cela ne démontre pas qu'il découvrira mieux des stratégies dans nos données. La documentation SB3 recommande elle-même une évaluation séparée et plusieurs runs, et souligne les besoins en interactions ainsi que la sensibilité au reward. [SAC](https://stable-baselines3.readthedocs.io/en/master/modules/sac.html), [Conseils d'évaluation SB3](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html).

Il faut également distinguer SAC « off-policy » et apprentissage hors ligne sur un historique fixe. Un historique de trades n'est pas automatiquement un jeu complet de transitions état/action/récompense pour notre portefeuille : il ne révèle pas toutes les décisions non exécutées ni ce qui se serait passé pour nos autres actions. Réentraîner dans un replay historique construit ces conséquences avec un simulateur et ses hypothèses. Cela ne dispense donc pas du travail sur l'exécution. [Levine et al., revue de l'offline RL](https://arxiv.org/abs/2005.01643).

Enfin, une architecture prévue pour des actions ne se transpose pas telle quelle à Polymarket. Le niveau de prix, entre zéro et un, y est une information centrale ; le principe du document consistant à privilégier les rendements sur les niveaux doit être adapté. Les côtés YES/NO, le paiement terminal et l'immobilisation du capital doivent aussi être représentés explicitement.

**Ce que le projet possède réellement**

Le point faible du plan actuel est que le premier MVP rend la comparaison visible avant de rendre la recherche automatique utilisable. La reprise du code montre que le raccordement est plus proche qu'un nouveau système RL :

- Les agents de tendance et retour à la moyenne ont des paramètres, mais le registre refuse encore les génomes différents des valeurs fixes. Le premier raccord est donc identifiable. [registry.py:127](C:/Dev/squad-ai/Brainstorming/GAN/prediction_market/src/pmx/agents/registry.py:127).
- Le mineur de règles contient une véritable recherche par faisceau, avec seuils calculés sur l'entraînement et budget de candidats. Ce n'est pas seulement une interface vide. [miner.py:62](C:/Dev/squad-ai/Brainstorming/GAN/prediction_market/src/pmx/rules/miner.py:62).
- La conversion des données du projet en table de recherche n'est pas branchée : `pmx rules --dataset` lève encore une erreur explicite. [cli_rules.py:88](C:/Dev/squad-ai/Brainstorming/GAN/prediction_market/src/pmx/cli_rules.py:88).
- Le module `optimizer` ne contient actuellement qu'une description. Il reste à créer l'orchestrateur des campagnes et à faire appliquer les règles candidates par des agents exécutables. [optimizer/__init__.py](C:/Dev/squad-ai/Brainstorming/GAN/prediction_market/src/pmx/optimizer/__init__.py).

Le moteur de backtest, les journaux et l'interface de résultats permettent de conserver une base commune. Leur existence ne certifie pas tous les aspects statistiques : notamment, un bootstrap avec moins de deux blocs retourne un intervalle dégénéré, tandis que le critère de promotion des règles ne contrôle pas explicitement ce nombre de blocs. Ce cas doit produire « incertitude non estimable ». [stats.py:231](C:/Dev/squad-ai/Brainstorming/GAN/prediction_market/src/pmx/metrics/stats.py:231), [tester.py:1113](C:/Dev/squad-ai/Brainstorming/GAN/prediction_market/src/pmx/rules/tester.py:1113).

**Le prochain jalon que je recommande**

Le parcours utilisateur devrait être : choisir un univers et un budget d'expériences, lancer la recherche, puis examiner des stratégies candidates avec leurs règles, coûts, résultats par période et raisons de rejet.

1. **Obtenir un corpus suffisant et contrôlé.** Conserver l'acquisition Polymarket Parquet proposée, en intégrant ses contrôles d'horodatage et de résolution. Raccorder le pipeline sur un échantillon représentatif pendant l'acquisition ; l'extraction de toute une blockchain n'est pas un préalable au développement. Les 287 marchés actuels permettent les essais fonctionnels, pas une affirmation de robustesse.
2. **Rendre la recherche paramétrique automatique.** Ouvrir les génomes validés, définir quelques familles et un budget initial, par exemple cinquante essais. Utiliser Optuna comme orchestrateur de paramètres ; garder tous les essais, y compris les échecs. Ce nombre est une limite de départ proposée, pas un seuil statistique universel.
3. **Raccorder la découverte de structures.** Construire la table causale depuis quelques variables réellement renseignées : niveau de prix, mouvements à différents horizons, volatilité, activité, âge de la dernière transaction et échéance connue à l'instant considéré. Le mineur pourra proposer des conjonctions courtes ; un adaptateur les traduira en décisions testables. Cette étape cherche des règles nouvelles, alors que la précédente ajuste seulement des familles connues.
4. **Comparer des finalistes gelés sur des périodes ultérieures.** Choisir avant la campagne l'objectif, les contraintes et les règles de sélection. La recherche et les réglages utilisent les fenêtres internes d'entraînement ; les périodes finales ne servent pas à guider Optuna. Afficher stabilité, risque, frais, nombre d'événements et sensibilité à l'exécution, en plus du rendement.

Optuna est une bibliothèque d'optimisation existante, avec espaces conditionnels, historique d'essais et stockage d'études. Elle peut éviter d'écrire un optimiseur maison. Elle ne fournit ni les signaux de marché, ni le protocole statistique : ceux-ci restent les responsabilités de pmx. [Documentation officielle](https://optuna.readthedocs.io/en/stable/).

Pour les exemples de l'utilisateur, deux questions doivent rester séparées : « un contrat à ce prix est-il sous-évalué par rapport au paiement final ? » et « ce retournement prédit-il un mouvement favorable dans les prochaines vingt-quatre ou quarante-huit heures ? ». Elles n'ont pas le même label, la même durée d'immobilisation ni la même sortie. L'horizon est fixé avant l'étude, pas choisi après avoir vu la meilleure courbe. Un prix de 0,90 n'est pas à lui seul un signal : il faut une estimation de valeur supérieure au prix, après coûts.

Les candidats devraient d'abord être évalués séparément avec le même capital et la même liquidité disponible. Le mode compétition avec liquidité partagée répond à une autre expérience : qui gagne lorsque plusieurs agents agissent simultanément ? Mélanger les deux ferait dépendre le classement d'une stratégie des autres candidats présents dans sa campagne.

**La place d'un modèle appris**

Si nous voulons un modèle qui découvre des interactions au-delà des règles courtes, mon premier choix serait **LightGBM**, entraîné sur nos observations et labels, avec capacité et recherche d'hyperparamètres limitées. C'est une bibliothèque de boosting d'arbres existante ; elle évite de définir d'emblée un environnement RL. Une politique explicite transforme ensuite son estimation en achat, vente ou abstention et limite l'exposition. [Documentation LightGBM](https://lightgbm.readthedocs.io/en/stable/).

Ce modèle doit battre une référence simple, notamment le prix de marché pour une prévision de résolution, puis démontrer un gain économique net dans le moteur. L'importance d'une variable n'est pas une preuve causale, et les règles extraites après lecture du test ne sont plus indépendamment validées. Le supervisé peut également surapprendre : ce choix facilite le diagnostic, il n'annule pas le problème.

Je garderais ensuite un emplacement pour un challenger SB3 standard, entraîné sur le même contrat d'observation/exécution. PPO pour une action discrète simple, ou SAC pour une allocation continue, se choisissent selon le problème réellement posé. Je ne rendrais ni les deux algorithmes, ni l'attention, ni les news obligatoires pour livrer la découverte de stratégies.

**Ce qui pourrait faire changer cette décision**

Un checkpoint accompagné de son environnement exact, de données accessibles, d'un protocole reproductible et d'un transfert positif sur notre univers pourrait devenir un accélérateur. Les vérifications actuelles n'ont pas établi cet ensemble pour les candidats du document. De même, si la difficulté mesurée devient surtout l'allocation séquentielle de capital entre signaux déjà valides, le RL gagnera en priorité.

Pour l'instant, je remonterais la recherche automatique au prochain jalon, en conservant les contrôles de données, plutôt que de lancer le Plan A SAC du document. Le produit attendu est une campagne de découverte inspectable ; le type de modèle est un composant remplaçable de cette campagne.
