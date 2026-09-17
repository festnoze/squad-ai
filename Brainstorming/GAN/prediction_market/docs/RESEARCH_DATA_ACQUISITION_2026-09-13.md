# Acquisition de données pour la recherche de stratégies : décision du 13 septembre 2026

**Décision : conserver Polymarket et importer une archive Parquet publique, versionnée, dans DuckDB local.** La source retenue est `TimeSeventeen/Polymarket-v1` sur Hugging Face. Commencer par les transactions binaires nettoyées et les événements de préparation/résolution des conditions : environ **13,37 Go** à télécharger. Le dépôt entier représente **52,72 Go**. Il n'est pas nécessaire de synchroniser Polygon pour obtenir ce premier corpus.

Cette recommandation répond à l'objectif exprimé : découvrir des règles sur les prix des marchés prédictifs, puis les confronter entre agents avec une validation robuste. Elle privilégie un démarrage local sans abonnement de données. Elle ne prétend pas déterminer le meilleur fournisseur pour toutes les formes de trading.

Recherche effectuée le 13 septembre 2026 : documentation primaire, comparaison des voies d'accès et petits contrôles réseau réels. Les preuves techniques sont conservées dans [DATA_ACQUISITION_PROBES_2026-09-13.json](DATA_ACQUISITION_PROBES_2026-09-13.json). Aucun téléchargement intégral, abonnement ou calcul de rentabilité n'a été lancé.

**Pourquoi cette source est le meilleur premier choix pour ce projet**

Le jeu est public, non soumis à une demande d'accès, et sa fiche annonce une licence CC BY 4.0. Il distribue une couche de transactions issues des événements `OrderFilled`, des couches alignées sur les marchés et des événements CTF. Ce sont des données de transactions ; le mot `daily` désigne le découpage des fichiers, pas une fréquence quotidienne des observations. [Fiche du producteur, révision consultée](https://huggingface.co/datasets/TimeSeventeen/Polymarket-v1/blob/5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa/README.md).

Les auteurs annoncent environ **1,20 milliard d'enregistrements de fills et 1,30 million de conditions de marché**, du **21 novembre 2022 au 28 avril 2026**. Ces chiffres décrivent l'ensemble étudié par les auteurs, pas le nombre de marchés indépendants qui seront admissibles dans notre premier corpus. Ils proviennent d'un préprint, et ne constituent pas notre audit de complétude. [Qin et Yang, préprint du 2 juin 2026](https://arxiv.org/abs/2606.04217).

J'ai vérifié l'inventaire public au commit `5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa`, puis additionné les tailles des fichiers de cette révision. Les Go ci-dessous sont décimaux ; le dépôt entier correspond aussi à environ 49,1 Gio.

| Couche mesurée | Fichiers | Taille | Usage proposé |
|---|---:|---:|---|
| `daily_aligned` | 1 248 | 13,175 Go | Premier corpus de transactions binaires |
| `CTF/preparations.parquet` et `CTF/resolutions.parquet` | 2 | 0,194 Go | Contrôle des conditions et des paiements finaux |
| `daily_aligned_multi` | 857 | 3,627 Go | Extension aux événements à plusieurs candidats après validation de leur représentation |
| `OrderFilled` | 42 | 27,383 Go | Vérification de la transformation et de la comptabilisation des transactions |
| Ensemble `CTF` | 5 | 8,535 Go | Préparations, résolutions, splits, merges et redemptions |

Les deux fichiers CTF de départ sont inclus dans la dernière ligne : ne pas additionner ces lignes comme des catégories disjointes. Tailles et nombres de fichiers sont mesurés via l'[API publique du dépôt](https://huggingface.co/api/datasets/TimeSeventeen/Polymarket-v1/tree/5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa?recursive=true&limit=1000), avec pagination, et conservés dans le fichier de preuves.

Trois petits fichiers ont réellement été téléchargés, lus avec PyArrow et comparés aux SHA-256 publiés : les trois correspondent. Deux contiennent respectivement 28 et 207 transactions alignées. La lecture HTTP partielle des métadonnées Parquet du 15 avril 2026 indique **4 387 421 lignes** ; celle des résolutions CTF indique **1 313 030 lignes**. Ce dernier nombre n'est pas un décompte vérifié de conditions uniques. Ces contrôles établissent l'accessibilité et la lisibilité, sans certifier tout le contenu.

Cette voie évite de construire d'abord un indexeur distribué. DuckDB peut interroger directement plusieurs fichiers Parquet et ne lire que les colonnes nécessaires ; les filtres peuvent aussi éviter des groupes de lignes lorsque leurs statistiques le permettent. Je propose de conserver les fichiers locaux et de construire des vues et agrégats, sans recopier tout l'historique dans une seconde base. Aucun benchmark de performance de notre futur importeur n'a encore été réalisé. [Documentation officielle DuckDB : Parquet](https://duckdb.org/docs/current/data/parquet/overview).

**Pourquoi « toute la blockchain » ne suffit pas**

Polymarket utilise une architecture hybride : la création et l'appariement des ordres passent hors chaîne, puis les transactions sont réglées sur chaîne. Les événements des contrats renseignent donc les exécutions et les opérations sur les positions. Ils ne donnent pas, à eux seuls, tous les ordres restés dans le carnet, leurs annulations ou leur priorité. Un nœud Polygon intégral ne reconstituerait pas magiquement cet historique manquant. [Polymarket, cycle de vie des ordres](https://docs.polymarket.com/concepts/order-lifecycle).

L'archive retenue couvre une période et une génération de contrats. Elle ne représente pas toute l'activité de Polymarket depuis sa création, ni l'état actuel du marché. Polymarket a migré vers son CLOB v2 le **28 avril 2026**, puis modifié ses API de données en septembre. Il faudra donc distinguer explicitement le régime v1 du régime actuel dans les conclusions de recherche. [Polymarket, changelog](https://docs.polymarket.com/changelog/predictions).

Mon choix consiste à acquérir un historique économique déjà indexé pour accélérer la recherche. Il ne vise pas un audit exhaustif de Polygon.

**Comparaison des voies étudiées**

| Voie | Ce qu'elle apporte | Motif de la décision |
|---|---|---|
| Archive TimeSeventeen + DuckDB | Historique de transactions, fichiers reproductibles, accès gratuit | **Retenue pour le premier corpus** ; ancien régime de marché et absence de carnet à signaler |
| Indexation des contrats via RPC ou fournisseur | Maîtrise de l'extraction, possibilité d'ajouter le régime actuel | Plus de développement : plages de blocs, reprises, contrats successifs, décodage, dédoublonnage et jointures métier |
| API officielles Polymarket | Métadonnées et flux récents | Les fenêtres et granularités documentées empêchent de les traiter comme un téléchargement intégral simple |
| CryptoHouse | SQL public immédiatement utilisable | La table de fills testée s'arrête au 5 janvier 2026 ; trop incomplète en récence pour être notre source principale |
| Goldsky Turbo | Extraction gérée, contrats v2 et livraison vers un stockage | Solution crédible pour une alimentation durable ; coût d'écriture à chiffrer avant un gros historique |
| PMXT | Historique de messages du carnet, utile pour l'exécution | Historique plus court et volume élevé ; à réserver à la validation d'exécution après les premiers candidats |
| Forex Dukascopy | Long historique de cotations bid/ask | Bon choix pour un projet Forex ; changement de cible injustifié ici par le seul nombre de ticks |

Les limites des API sont concrètes. Le flux global `/v2/trades` est limité au mois courant et au précédent. Les requêtes par condition ou événement ont une fenêtre de trois ans et ignorent les bornes temporelles utilisées dans d'autres modes. Une boucle de pagination globale ne garantit donc pas toute l'histoire. [Polymarket, endpoint des trades](https://docs.polymarket.com/api-reference/feeds/list-trades).

Pour les prix, la documentation distingue des rétentions glissantes fines et des archives permanentes plus grossières : une minute sur au moins sept jours, cinq minutes sur au moins soixante jours, trente minutes sur au moins quatre-vingt-dix jours ; l'historique permanent est à douze heures, avec trois heures à partir de juillet 2026. Ce sont des garanties documentées, pas des mesures de densité pour chaque marché. [Polymarket, Data API](https://docs.polymarket.com/api-reference/data-api/overview).

J'ai réellement interrogé CryptoHouse avec son accès public documenté. Le `min/max(timestamp)` de `polymarket.orders_filled` retourne le 21 novembre 2022 et le **5 janvier 2026**, sur 257 649 337 lignes physiques. Ce résultat porte sur cette table, sans réconciliation de ses versions, et ne permet pas de conclure sur toutes les autres tables. Les requêtes et résultats exacts sont dans les preuves. [Instructions d'accès du mainteneur](https://github.com/ClickHouse/CryptoHouse#direct-connections).

Goldsky prévient que ses anciens subgraphs publics ne sont plus fiables après la migration d'avril ; ses flux Turbo documentent les contrats v2. Il serait pertinent pour une ingestion continue, après vérification de la couverture des différentes générations. [Goldsky, intégration Polymarket](https://docs.goldsky.com/chains/polymarket).

Le tarif publié de Goldsky inclut un million d'écritures gratuites, puis 1 $ par 100 000 jusqu'à 100 millions et 0,10 $ par 100 000 au-delà. À titre de calcul, un milliard d'écritures représente environ **1 890 $**, hors calcul et stockage, avant application d'éventuels crédits. Ce n'est pas un devis pour notre corpus : le nombre de sorties dépend du flux et de la transformation. [Goldsky, tarification consultée](https://docs.goldsky.com/pricing/summary).

PMXT v2 annonce une archive de messages de carnet depuis le 13 avril 2026, publiée en fichiers horaires, sous CC BY 4.0. Ses 100 à 400 Mo par heure annoncés représentent, par calcul, environ 72 à 288 Go sur trente jours. Une grande partie des lignes sont des changements de prix : elles ne sont pas autant de transactions. C'est une piste pour vérifier plus tard spreads, liquidité et prix exécutables ; elle ne remplace pas notre premier historique de marchés résolus. [PMXT, documentation du producteur](https://archive.pmxt.dev/docs/v2-data-overview).

Les appels directs à Gamma et à la Data API ont par ailleurs échoué ici sur une erreur de certificat TLS ne correspondant pas au nom de domaine. La vérification TLS a été conservée. Cette observation locale n'est pas une conclusion générale sur la disponibilité ou le droit d'accès à Polymarket ; le dépôt public retenu, lui, est accessible depuis cet environnement.

**Pourquoi je ne choisirais pas Forex ou actions maintenant**

Dukascopy propose effectivement des données historiques gratuites, du tick aux périodes longues, notamment via son outil d'export. Son flux historique fournit les meilleurs bid/ask et les volumes proposés correspondants, et non les quantités effectivement échangées. La FAQ indique aussi que la profondeur historique du carnet n'est pas conservée. Les cotations permettent de modéliser un spread, mais notre plafond de participation au volume traité ne pourrait pas être appliqué à ces volumes sans changer de sens. [Dukascopy, historique](https://www.dukascopy.com/swiss/english/marketwatch/historical/) ; [Dukascopy, FAQ technique](https://www.dukascopy.com/swiss/english/about/faq/).

Cependant, le Forex est décentralisé et fragmenté. Le flux d'un fournisseur ne représente pas une bande consolidée de toutes les transactions mondiales ; il faut interpréter ses volumes dans le périmètre de ce flux. [BIS, structure d'exécution du marché FX, décembre 2025](https://www.bis.org/publications/fx-trade-execution-landscape-through-prism-2025-bis-triennial-survey).

Surtout, la quantité de ticks répond mal à notre question. Un million de cotations EUR/USD ne constitue pas un million d'événements indépendants dont on observe ensuite la résolution. Les recherches « acheter des contrats proches de 90 % », « comportement à l'approche de l'échéance » et « retournement avant la résolution » ont une structure naturelle sur les contrats prédictifs. Leur équivalent Forex doit être redéfini : horizon de sortie, objectif de rendement, stop, exposition et financement.

Les actions disposent également de voies abordables : Alpaca annonce un historique depuis 2016 et un plan gratuit limité à 200 requêtes par minute. Sa FAQ précise que les données historiques consolidées SIP sont accessibles sans abonnement si la borne de fin précède les quinze dernières minutes, avec authentification. Je n'ai pas testé de compte ni vérifié la couverture complète des titres retirés de cote. [Alpaca, offre de données](https://docs.alpaca.markets/us/docs/about-market-data-api) ; [Alpaca, FAQ historique](https://docs.alpaca.markets/us/docs/market-data-faq).

Les actions ajouteraient un autre univers et d'autres traitements : titres retirés de cote, distributions, changements de capital et calendriers. Le projet possède déjà un type `ContinuousInstrument`, donc un futur élargissement ne demanderait pas de tout réécrire. Il demanderait néanmoins des règles d'exécution et des parcours de recherche supplémentaires. Je conserverais cette possibilité, sans l'inclure dans la première acquisition.

L'objection valable à mon choix serait un objectif différent : chercher immédiatement des règles génériques sur des cotations bid/ask, avec peu d'intérêt pour les probabilités ou la résolution des événements. Dans ce cas, un premier univers Forex homogène pourrait être plus direct. Ce n'est pas l'objectif exprimé ici. Je ne conclus pas non plus que Polymarket serait plus facile à battre : les sources consultées ne le démontrent pas.

**La méthode unique à implémenter**

Le pipeline proposé est : **archive figée → import local vérifié → vues DuckDB → dataset de recherche pmx**. Les étapes ci-dessous appartiennent à la même chaîne d'acquisition.

1. **Figer la source.** Enregistrer le dépôt, son commit, les fichiers retenus, leurs tailles, leurs empreintes et la licence. Télécharger avec reprise et validation avant renommage définitif. Conserver l'attribution. La provenance doit rester consultable depuis chaque dataset produit.
2. **Importer le premier corpus complet de cette sélection.** Prendre `daily_aligned`, `CTF/preparations.parquet` et `CTF/resolutions.parquet`, soit 13,37 Go. Avant de généraliser, auditer un petit échantillon réparti sur plusieurs périodes, tailles de marchés et catégories. Prévoir environ 30 à 50 Go de disque libre pour cette première sélection, les agrégats et les fichiers temporaires ; c'est une marge de travail proposée, pas une taille mesurée des futurs dérivés.
3. **Séparer observations et résultats.** Exposer aux agents uniquement les informations disponibles à l'instant de décision. Garder les issues finales dans des tables de labels séparées. Représenter le côté du contrat, les unités et les heures explicitement. Les résolutions non binaires ou ambiguës sortent du premier corpus avec un motif visible.
4. **Produire une grille horaire pour les premiers signaux de quelques heures à deux jours.** Garder les transactions sources pour affiner ensuite. Calculer prix et volumes à partir des observations antérieures à la décision ; conserver le nombre de trades, l'ancienneté du dernier trade et les trous. Une absence de transaction ne devient pas une preuve de prix exécutable constant. Une grille plus fine ne crée aucune information nouvelle sur un marché inactif.
5. **Publier un manifeste de qualité et brancher le moteur existant.** Le front doit montrer le nombre de marchés admissibles, la période, les groupes d'événements, la fréquence réelle des observations, les exclusions et les limites de liquidité. Les agents peuvent alors confronter quelques règles préspécifiées sur le même corpus, avec les mêmes hypothèses de coûts.

La couche `OrderFilled` restera la référence disponible pour contrôler la transformation sur des partitions choisies ; son téléchargement intégral n'est pas un préalable à l'exploration. Les marchés à plusieurs candidats pourront rejoindre ce même pipeline après validation de leur regroupement et de leur comptabilité. Ils ne doivent pas être présentés comme déjà inclus dans le premier périmètre binaire.

L'acquisition peut s'appuyer sur `snapshot_download` du client officiel Hugging Face : sélection des fichiers et révision explicites, sans écrire un crawler. Le cœur du téléchargement serait le suivant, une fois la dépendance installée dans l'environnement du projet. Cet exemple n'a pas été exécuté : il téléchargerait la sélection complète, environ 13,37 Go. La lecture et les contrôles du dataset restent à implémenter autour de lui. [Hugging Face, guide officiel de téléchargement](https://huggingface.co/docs/huggingface_hub/guides/download).

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="TimeSeventeen/Polymarket-v1",
    repo_type="dataset",
    revision="5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa",
    allow_patterns=[
        "README.md",
        "daily_aligned/*.parquet",
        "CTF/preparations.parquet",
        "CTF/resolutions.parquet",
    ],
    local_dir=r"C:\Dev\squad-ai\Brainstorming\GAN\prediction_market\data\external\polymarket-v1",
)
```

**Ce qui doit être vérifié avant d'interpréter les résultats**

Les petits fichiers lus révèlent deux points concrets : la couche alignée ne porte pas le champ `id` de la couche `OrderFilled`, et les résolutions CTF ne portent pas d'horodatage dans leur schéma. Il faut donc préserver au minimum fichier, révision et rang de ligne pour la traçabilité ; une clé de provenance n'est pas à elle seule un identifiant d'exécution économique. L'heure de disponibilité d'un résultat nécessite une source validée, par exemple l'horodatage du bloc de résolution. Le seul paiement final ne donne pas cette heure. Tant que ce contrôle n'est pas acquis, le règlement des positions et la durée d'immobilisation du capital ne peuvent pas être présentés comme reproduits fidèlement.

La fiche du producteur présente les métadonnées comme un instantané figé. Elle contient aussi des indications contradictoires sur UTC et UTC+8. Nous reconstruirons les partitions temporelles depuis les timestamps des transactions plutôt que de supposer que le nom du fichier constitue une heure de marché. L'étiquette gagnante et une date de résolution connue après coup ne deviennent jamais des variables d'entrée historiques. [Fiche technique versionnée](https://huggingface.co/datasets/TimeSeventeen/Polymarket-v1/blob/5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa/README.md).

L'audit devra également contrôler les unités monétaires, les côtés YES/NO ou Up/Down, les transactions répétées, les effets de routeurs et les montants comptés deux fois. Un montant payé par un acteur ne doit pas être assimilé sans vérification au coût de notre agent simulé. L'importeur actuel du projet fixe un barème Polymarket nul ; cette hypothèse devra être remplacée par une représentation des frais adaptée aux périodes et aux marchés utilisés.

L'univers admissible doit être défini à la date de décision, sans sélectionner rétrospectivement seulement les marchés déjà résolus à la fin de la période. Les marchés encore ouverts restent sans label disponible, avec un traitement explicite de cette censure. Une archive de transactions ne constitue pas, à elle seule, le catalogue des marchés qui n'ont jamais échangé. Enfin, l'importeur actuel rapproche la date de clôture de la date de résolution connue après coup : cette transformation ne doit pas alimenter une variable temporelle présentée comme historiquement observable.

Pour éviter que le volume de données ne serve surtout à produire du surapprentissage, je fixerais les règles suivantes avant le premier classement :

- Décompter les conditions, les groupes d'événements et les opportunités effectives, en plus des transactions. Garder ensemble les marchés liés ; traiter explicitement les séries récurrentes très corrélées.
- Séparer chronologiquement découverte, validation et test final, avec exclusion des observations dont les fenêtres ou labels chevauchent une frontière. Réserver le test final avant l'optimisation et ne pas le recycler après chaque échec.
- Limiter et journaliser les variantes de stratégies essayées. Examiner la stabilité entre périodes et familles de marchés ; corriger la sélection multiple et estimer l'incertitude par groupes, pas en supposant chaque tick indépendant.
- Distinguer résultat de prédiction et argent simulé. Tester plusieurs hypothèses prudentes de coûts et d'exécution ; signaler l'absence de profondeur historique. Une stratégie intéressante dans cette archive devient une candidate à tester sur des cotations récentes et en simulation prospective.

Exemple : acheter à 0,90 un contrat qui paie réellement 1 dans 90 % des cas a une espérance brute nulle. Neuf gains de 0,10 compensent une perte de 0,90. Le signal à découvrir est donc une différence robuste entre le prix payé et la probabilité de paiement, après coûts et immobilisation du capital ; le taux de réussite seul ne suffit pas.

**Premier jalon attendu.** Un dataset Polymarket large, reproductible, documenté et exploitable par les agents, avec un écran permettant d'en inspecter la couverture et les exclusions. Le critère de réussite est la qualité du corpus et de son intégration. La découverte d'une stratégie gagnante reste une hypothèse à tester ; l'acquisition de davantage de lignes ne la garantit pas.
