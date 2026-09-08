# Agents IA monétisables via CLI / MCP : partir des besoins

Recherche du 6 septembre 2026. Prolongement des trois listes précédentes et du [comparatif](COMPARATIF_IDEES.md). Les clients visés restent principalement hors développement logiciel ; CLI et MCP sont les interfaces de livraison du produit.

## Ce que je construirais en premier

**Un agent de préparation et de contrôle de catalogues fournisseurs**, utilisable sur des fichiers avant toute intégration. Deuxième choix : **un agent de diagnostic des produits refusés dans Merchant Center**, vendu aux agences e-commerce. Troisième choix : **un agent qui contrôle la complétude des dossiers d’appels d’offres et leurs modifications**.

Le besoin commun : « j’ai des informations dispersées ; une anomalie bloque une opération ; trouve les preuves, prépare la correction et montre-moi ce qui reste à décider ». Cette tâche est plus précise et mesurable qu’un assistant administratif généraliste.

J’interprète la demande comme des **idées d’agents à développer et commercialiser**, en réutilisant des accès CLI/MCP existants lorsqu’ils conviennent. Les noms, commandes et outils métier proposés ci-dessous sont fictifs : aucun de ces nouveaux agents n’est déjà installé ou implémenté ici.

## Ce qui est établi, et ce qui reste une hypothèse

La recherche a trouvé des documentations officielles décrivant les problèmes traités, des produits concurrents et plusieurs interfaces exploitables. Cela confirme des catégories de travail réelles et une faisabilité partielle. Cela ne prouve pas qu’un client paiera notre offre, ni qu’une intégration fonctionnera sans essai.

La majorité des sources proviennent de fournisseurs : elles sont utiles pour connaître les fonctions existantes et la concurrence, mais ne constituent pas une étude indépendante de demande. Aucun entretien client ni benchmark sur des données réelles n’a été réalisé. Les prix, délais, scores et seuils de validation ci-dessous sont nos hypothèses de test.

## Pourquoi CLI / MCP peut aider à vendre

Un responsable achats achète une comparaison exploitable ; une agence achète un moyen de traiter plusieurs comptes. L’interface technique intéresse surtout **l’intégrateur, l’agence ou l’équipe opérations équipée d’un assistant IA**.

- **CLI** : traitements de lots, fichiers locaux, planification externe et résultats JSON reproductibles.
- **MCP** : permet à un assistant compatible d’appeler les fonctions métier et d’en récupérer les preuves sans nouvelle interface dédiée. MCP expose notamment outils, ressources et prompts ; ce n’est pas à lui seul un agent autonome. [Documentation du SDK MCP](https://ts.sdk.modelcontextprotocol.io/server).
- **Produit payant** : règles sectorielles, rapprochements vérifiés, mémoire des corrections, suivi des exceptions, connecteurs entretenus et résultats réutilisables. Un simple accès à une API sera difficile à défendre.

Il faut distinguer **les MCP utilisés en entrée** (CRM, helpdesk…) du **MCP de notre agent**, qui exposera une tâche complète comme `catalog_validate_batch`. Le client peut acheter un service piloté par une agence avant de savoir utiliser MCP lui-même.

## Classement orienté besoins

Notes sur 5, 5 étant le plus favorable. « Besoin » apprécie proximité d’un coût ou blocage concret et capacité à identifier un acheteur ; « Facilité » inclut accès aux données et contrôle du résultat ; « MCP » mesure l’intérêt d’intégration, pas sa disponibilité actuelle. Ordre de priorité qualitatif pour un solo, pas classement de taille de marché.

| Rang | Besoin exprimé par le client | Agent proposé | Payeur / utilisateur | Besoin | Facilité | MCP | Prix mensuel à tester, volume borné |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | Mettre les références fournisseurs en vente sans ressaisie et erreurs | CatalogReady | Distributeur / agence catalogue | 4 | 4 | 5 | 149–399 € / catalogue |
| 2 | Comprendre et corriger les refus qui rendent des produits inéligibles | FeedRepair | Agence Shopping / e-commerçant | 4 | 3 | 5 | 99–249 € / boutique |
| 3 | Ne pas manquer une pièce ou un changement dans un appel d’offres | BidCheck | PME déjà candidate / cabinet spécialisé | 4 | 4 | 4 | 149–399 € / équipe |
| 4 | Comprendre les écarts commande–livraison–facture avant validation | PurchaseExceptions | PME distributrice / responsable achats | 4 | 2 | 5 | 249–699 € / entité |
| 5 | Décider d’un renouvellement fournisseur avant la date de préavis | RenewalDesk | Responsable opérations / DAF à temps partagé | 3 | 4 | 4 | 79–249 € / portefeuille |
| 6 | Corriger les incohérences CRM sans perdre l’historique commercial | CRMRepair | Agence RevOps / direction commerciale | 3 | 3 | 5 | 99–299 € / portail |
| 7 | Éviter que les mêmes erreurs de support se répètent | SupportFix | Responsable support / agence e-commerce | 3 | 3 | 5 | 149–399 € / marque |
| 8 | Obtenir les justificatifs manquants sans relances désordonnées | EvidenceDesk | Cabinet comptable / assistant administratif | 3 | 3 | 4 | 99–299 € / cabinet, petit lot de dossiers |

Ces tarifs concernent un futur produit, avec quotas et support limité, pas une prestation humaine illimitée. Ils sont donc différents des honoraires de service proposés dans ideas3. La différence doit être permise par une réduction **mesurée** du temps opérateur.

## 1. CatalogReady — agent de préparation des catalogues

**Situation de départ.** Un distributeur reçoit trois fichiers Excel et un PDF pour une nouvelle gamme. Les noms de colonnes varient, certains produits sont en doublon, des dimensions sont absentes et l’import dans le catalogue échoue.

**Signal documenté.** Akeneo décrit précisément collecte, normalisation, enrichissement et validation des données fournisseurs dans Supplier Data Manager. Le besoin a donc déjà une catégorie de solutions ; nous devons trouver un segment mal servi, pas prétendre inventer le problème. [Akeneo SDM](https://www.akeneo.com/supplier-data-manager/).

**Travail de l’agent.** Lire le schéma cible ; identifier les références ; proposer les correspondances de colonnes ; vérifier unités, variantes et champs obligatoires ; retrouver la source de chaque valeur ; préparer un fichier importable et une liste de questions fournisseur. Apprendre les mappings acceptés pour le prochain lot.

**Pourquoi de l’IA ?** Comprendre les libellés hétérogènes et rapprocher les références ambiguës. Les conversions numériques, formats et règles de présence restent déterministes. Avec un fournisseur déjà standardisé, un simple mapping peut suffire.

**Interfaces.** MVP local CSV/XLSX/PDF ; adaptation à une API e-commerce ensuite. Shopify fournit une API Admin GraphQL pour les produits. Le MCP Storefront est destiné à des usages de boutique et ne doit pas être assimilé à un accès général d’administration. [Shopify Admin](https://shopify.dev/docs/api/admin-graphql/latest/queries/products), [Storefront MCP](https://shopify.dev/docs/apps/build/storefront-mcp/servers/storefront).

**Offre test.** Pilote de 100 références simples à 300–500 €, puis 199 €/mois jusqu’à 500 références traitées, un schéma cible, deux formats fournisseur connus. Nouveaux mappings complexes facturés séparément. Canal : agences qui intègrent des catalogues, puis distributeurs d’un seul secteur.

**Ce qui pourrait nous différencier.** Fonctionner sur les exports déjà disponibles, livrer des preuves champ par champ, et gérer les anomalies d’une niche. Akeneo couvre déjà une grande partie du problème : « moins cher qu’un PIM » ne suffit pas à créer un avantage durable.

**Test décisif.** Sur 100 références annotées par le client, réduire d’au moins moitié le temps humain total, avec aucun champ critique erroné dans les lignes acceptées ; les autres doivent être bloquées explicitement. Obtenir un deuxième lot payé. Première version bornée : estimation de 7–12 jours de travail, hors vente et connecteurs de production.

## 2. FeedRepair — agent de diagnostic des flux marchands

**Situation.** Une agence découvre que des références ne sont plus éligibles à un canal de diffusion. Il faut comparer le diagnostic Google, la fiche boutique et le flux, puis savoir où corriger la valeur.

**Signal documenté.** Merchant API expose données produit et problèmes associés ; les outils de gestion de flux comme DataFeedWatch proposent déjà leur revue. [Google Merchant API](https://developers.google.com/merchant/api/guides/products/list-products-data-issues), [DataFeedWatch Feed Review](https://www.datafeedwatch.com/blog/feed-review).

**Travail.** Regrouper les erreurs par cause ; comparer les faits disponibles ; produire une modification proposée et localisée ; signaler les problèmes de politique qui demandent une autre démarche ; après correction approuvée, vérifier le statut ultérieur. Une correction soumise n’est pas une réacceptation.

**IA versus règles.** Les contrôles de présence et comparaisons de prix restent des règles ; l’IA relie les observations dispersées et explique la correction. Elle ne fabrique pas de GTIN et ne déduit pas un attribut absent.

**Interfaces.** Merchant API officielle + export ou API de la boutique ; notre CLI/MCP métier reste à écrire. Aucun MCP officiel Merchant n’a été vérifié dans cette recherche. Le MVP peut analyser un export de diagnostics, mais ne pourra alors pas confirmer seul la réacceptation.

**Offre.** Audit payé 250 € sur une boutique, puis 149 €/mois pour une boutique et jusqu’à 1 000 produits contrôlés par semaine, avec modifications validées. Vendre d’abord à une agence gérant plusieurs boutiques. La taille de lot doit être confrontée aux quotas et coûts réels.

**Différenciation à tester.** La chaîne « diagnostic → source exacte → correction → résultat observé », avec historique multi-comptes. Un rapport d’erreurs seul est trop proche du produit natif.

**Test.** Constituer 30 erreurs connues ; vérifier les causes et les corrections proposées ; suivre les erreurs effectivement disparues. Ne pas promettre un gain de ventes, ni la résolution des suspensions de compte. Estimation MVP : 10–15 jours, sur un seul couple Google + boutique.

## 3. BidCheck — contrôle des pièces et changements d’appels d’offres

**Situation.** Une PME sait à quel marché répondre, mais doit lire un dossier volumineux, répartir les pièces et repérer les modifications publiées après la première lecture.

**Signal.** L’API BOAMP est documentée et gratuite. Loopio commercialise la gestion des réponses et a publié une enquête auprès de plus de 1 500 entreprises ; cela signale une charge de travail organisée, sans être une mesure du marché des petites PME françaises. [API BOAMP](https://www.data.gouv.fr/dataservices/api-bulletin-officiel-des-annonces-des-marches-publics-boamp), [Enquête Loopio 2025](https://loopio.com/blog/loopio-releases-sixth-annual-rfp-response-trends-and-benchmarks-report/).

**Agent.** Transformer le règlement et les pièces en matrice d’exigences avec références de pages ; rapprocher chaque exigence des justificatifs fournis ; signaler les absences et contradictions ; comparer deux versions du dossier ; préparer des questions pour le responsable. Le résultat est un contrôle de complétude documentaire, pas une certification de recevabilité.

**Interfaces.** CLI sur dossier local en premier ; API BOAMP pour découvrir les avis. L’accès BOAMP ne garantit pas l’accès à tout le DCE, aux portails acheteurs ou aux amendements. Le client peut déposer les versions reçues ; chaque portail supplémentaire constitue un chantier distinct.

**Offre.** 150–300 € pour analyser un dossier passé, puis 249 €/mois pour quatre dossiers simples, plafonnés en pages et versions. Cible : cabinets de réponse aux marchés ou PME candidates régulières. Éviter les entreprises qui n’ont ni capacité de réponse ni justificatifs.

**Différenciation.** Preuves et suivi des changements dans une spécialité, par exemple nettoyage. Un rédacteur généraliste de mémoires techniques est plus difficile à vérifier et déjà concurrentiel.

**Test.** Rejouer dix dossiers historiques avec leur checklist validée : aucune exigence obligatoire connue omise dans ce jeu, contradictions signalées et temps de vérification réduit. Cela ne garantit pas les dossiers futurs. Estimation MVP : 7–10 jours, sans soumission ni surveillance universelle des portails.

## 4. PurchaseExceptions — rapprochement achats et dossiers d’écarts

**Situation.** Une facture mentionne 24 cartons, le bon de commande 144 unités et la livraison 120 unités. Quel écart est réel, quelle information manque, et qui doit répondre ?

**Signal.** Precoro documente le rapprochement commande/facture/réception, les tolérances et un matching amélioré par IA. Le rapprochement lui-même est donc déjà vendu. [Precoro matching](https://help.precoro.com/matching-process), [Rapprochement à trois pièces](https://help.precoro.com/3-way-match-functionality).

**Agent.** Reconstituer un dossier de pièces, rapprocher lignes et unités, appliquer les tolérances approuvées, préparer les questions et suivre les exceptions. Si l’équivalence carton/unité n’est pas documentée, la conversion reste bloquée. Calculs effectués par code, pas par génération de texte.

**Accès.** CLI sur exports et pièces ; MCP métier à construire. Ne pas dépendre d’un connecteur ERP universel. Choisir un format d’export et un secteur ; l’accès aux pièces de réception est un prérequis de vente.

**Offre.** Pilote 500–900 € sur 50 dossiers ; abonnement hypothétique de 399 €/mois pour 200 dossiers simples, sans validation de paiement. Canal : intégrateurs ERP et responsables achats de distributeurs.

**Avantage possible.** Traiter les exceptions qui restent hors du système existant et réunir leurs preuves. Si l’ERP les résout déjà, pas de raison d’ajouter l’agent.

**Validation.** Mesurer faux rapprochements, dossiers non résolus et temps de contrôle sur des cas normaux et litigieux. Un montant présenté comme « anomalie » n’est pas une économie réalisée. MVP estimé : 15–25 jours ; commencer par un audit de fichiers sans écriture comptable ni paiement.

## 5. RenewalDesk — échéances de préavis et dossiers de décision

**Situation.** Un contrat finit en décembre mais impose une décision bien avant. Le propriétaire interne n’est pas identifié et un avenant a changé les dates.

**Signal.** Vendr gère les clauses de reconduction et utilise le préavis pour déterminer la date limite. Un calendrier seul est donc un produit déjà couvert. [Vendr : reconduction automatique](https://help.vendr.com/en/articles/9130857-working-with-contracts-that-have-an-auto-renewal-clause).

**Agent.** Lire contrat et avenants, citer les passages pertinents, construire une chronologie à confirmer, identifier les informations manquantes et préparer un dossier de décision avec responsable assigné. Les clauses ambiguës demandent une revue spécialisée ; l’agent ne décide pas de leur portée juridique.

**Accès.** MVP local PDF et export de fournisseurs ; accès messagerie/Drive et calendrier seulement après vérification des API, droits et périmètre. MCP métier à construire ; aucun connecteur Vendr n’est présumé disponible.

**Offre.** Audit de 20 contrats pour 250–400 €, puis 129 €/mois jusqu’à 50 contrats actifs avec changements bornés. Cible : DAF externalisé ou office manager gérant plusieurs entités. Éviter la TPE avec seulement trois contrats.

**Validation.** Comparer dates et préavis à un registre annoté ; confronter tous les contrats avec avenants. Mesurer décisions prises avant les dates limites, pas des économies supposées. Ni résiliation ni négociation automatique. MVP : 5–8 jours ; la valeur récurrente reste plus incertaine que la vente d’un audit.

## 6. CRMRepair — maintenance des incohérences commerciales

**Situation.** Plusieurs imports produisent des sociétés en doublon, des opportunités sans responsable et des associations incohérentes. Le suivi commercial devient peu fiable.

**Signal.** HubSpot propose déjà des outils de qualité et de dédoublonnage. Son MCP officiel donne des accès CRM en lecture et écriture selon les objets et permissions. [Qualité des données HubSpot](https://www.hubspot.com/products/data-quality-software), [MCP HubSpot](https://developers.hubspot.com/ai-tools/mcp).

**Agent.** Auditer un ensemble de règles propres au client, rechercher les preuves d’identité, expliquer les incohérences, produire une liste de corrections et conserver l’avant/après. L’intérêt potentiel est la cohérence entre processus métier et plusieurs sources, pas simplement « trouve les doublons ».

**Accès.** Réutiliser le MCP CRM distant officiel ou l’API ; ne pas le confondre avec le MCP développeur local. La disponibilité générale du MCP ne prouve pas qu’une opération de fusion donnée est exposée : inventorier les outils sur un compte de test avant de la promettre. MVP export-only possible.

**Offre.** Audit à 300 €, puis 149 €/mois, un portail et cinq règles métier sur un volume borné. Canal privilégié : agence RevOps qui réutilise les mêmes contrôles chez plusieurs clients.

**Validation.** Tester sur un export avec doublons réels et homonymes. Les propositions de fusion restent revues ; certains changements ne sont pas facilement annulables. Stopper si les outils natifs donnent le même résultat. MVP lecture seule : 7–10 jours.

## 7. SupportFix — correction des causes répétées de tickets

**Situation.** Les mêmes questions sur une politique de retour ou une variante produit génèrent des tickets. Il faut retrouver la cause, corriger le contenu et vérifier si le problème revient moins.

**Signal et concurrence forte.** Le MCP Gorgias, actuellement documenté comme bêta, permet analyse des tickets et actions sur le helpdesk. L’analyse générique des thèmes est déjà un exemple officiel. Notre offre doit se concentrer sur une boucle de correction mesurée. [MCP Gorgias](https://docs.gorgias.com/en-US/connect-your-ai-assistant-to-the-gorgias-mcp-6310546).

**Agent.** Regrouper les tickets avec exemples, identifier la source manquante ou contradictoire, proposer une correction de FAQ ou de fiche, la tester contre des cas historiques et comparer le taux de recontact après publication approuvée. Une cause supposée reste étiquetée comme hypothèse.

**Accès.** MCP Gorgias officiel pour les fonctions disponibles au rôle ; API boutique ou exports pour le produit. MVP avec fichiers puis validation sur compte test. Éviter de présenter un ensemble de prompts existants comme une technologie exclusive.

**Offre.** Sprint 400–600 €, puis 249 €/mois jusqu’à 1 000 tickets analysés et cinq propositions de correction ; pas de service client illimité. Acheteur : responsable support d’une marque avec volume récurrent.

**Test.** Choisir un motif fréquent, tester le correctif, mesurer les tickets concernés pour 100 commandes en contrôlant autant que possible saisonnalité et mix produit. Une baisse brute de tickets n’établit pas l’effet de l’agent. MVP : 8–12 jours. Abandonner si le client obtient déjà le résultat avec son outil natif.

## 8. EvidenceDesk — collecte des pièces manquantes

**Situation.** À chaque préparation mensuelle, des opérations n’ont pas de justificatif ; plusieurs personnes relancent le même interlocuteur sans savoir ce qui a été reçu.

**Signal et raison du classement bas.** Dext propose déjà un rapport de pièces manquantes et des demandes de justificatifs. Il faut d’abord vérifier les fonctions en place, car ce problème peut déjà être résolu sans nouvel agent. [Dext : pièces manquantes](https://help.dext.com/en/articles/106085-using-the-missing-paperwork-report-in-dext), [Demandes de pièces](https://help.dext.com/en/articles/416736-how-to-request-paperwork-for-bank-transactions-in-dext).

**Agent.** Rapprocher un export d’opérations avec des documents, identifier les ambiguïtés, attribuer les demandes, préparer un seul brouillon par interlocuteur et arrêter les relances quand la pièce est reçue. Ne pas produire de déclaration fiscale ni interpréter la déductibilité.

**Accès.** CSV et fichiers pour le pilote. API de messagerie et connecteur comptable spécifiques ultérieurement ; aucun MCP officiel Dext n’est confirmé ici. Séparer chaque dossier client et son historique de demandes.

**Offre.** Pilote 200–400 € pour trois dossiers, puis 199 €/mois jusqu’à dix petits dossiers et 500 opérations au total. Tester auprès d’un cabinet qui rencontre des problèmes entre plusieurs systèmes, pas auprès d’un utilisateur Dext satisfait.

**Validation.** Rejouer un mois annoté, mesurer temps humain et faux rapprochements ; tester les documents manquants et les pièces déjà reçues. Aucun envoi automatique sans mandat et règles établies. MVP sur fichiers : 7–12 jours.

## Interfaces vérifiées et éléments restant à construire

« Vérifié » signifie documentation officielle consultée, pas connexion effectuée ou capacité testée dans cet environnement.

| Brique | Statut observé | Usage envisageable | Limite importante |
|---|---|---|---|
| HubSpot CRM MCP | Officiel, lecture/écriture documentées | CRMRepair | Scopes et opérations précises à vérifier sur compte test |
| Gorgias MCP | Officiel, bêta documentée | SupportFix | Rôle utilisateur, stabilité et outils réellement accessibles |
| Airbyte Agent CLI / MCP | Interfaces officielles documentées | Accès à plusieurs systèmes | Couverture exacte, coûts, conditions et permissions à vérifier pour chaque connecteur |
| Google Merchant API | API officielle | FeedRepair | Notre adaptateur CLI/MCP reste à développer |
| Shopify Admin GraphQL | API officielle | CatalogReady / FeedRepair | Autorisation boutique requise ; ne pas confondre avec Storefront MCP |
| BOAMP | API publique officielle | BidCheck | Ne fournit pas à elle seule tout le circuit de récupération des DCE |
| Fichiers locaux | Interface du MVP que nous développerions | Les huit agents | Parsing, OCR, droits d’accès et formats encore à tester |

Airbyte expose une CLI et un MCP pour accéder à des systèmes métier ; cela peut éviter de refaire une couche de connexions. Cette infrastructure est à comparer aux API directes après choix du besoin, pas à acheter avant un pilote. [Airbyte Agent CLI](https://airbyte.com/agent-cli), [Airbyte MCP](https://airbyte.com/blog/agent-mcp).

## À quoi ressemblerait le produit ?

Exemples de contrats d’interface **proposés, non exécutables à ce stade** :

```text
catalogready analyze --input ./supplier-batch --schema ./catalog-schema.json --output ./review
feedrepair diagnose --account demo-store --mode read-only --output ./review
bidcheck compare --previous ./dce-v1 --current ./dce-v2 --output ./changes
```

Le MCP exposerait des opérations métier bornées : `catalog_analyze_batch`, `catalog_get_evidence`, `catalog_prepare_patch`, `catalog_apply_approved_patch`. Chaque résultat porte un identifiant de traitement, sa version de source, les propositions, les preuves et les exceptions.

Un seul moteur métier sert la CLI et MCP. Une tâche longue renvoie un identifiant puis permet de lire son statut. Le traitement continue dans un worker ; la planification est assurée par un ordonnanceur externe. **MCP seul ne garantit ni exécution en arrière-plan ni suivi des tâches.**

Pour passer du prototype au produit : opérations idempotentes, budgets de traitement, isolation des clients, historique des versions et validations ciblant exactement la modification proposée. Les instructions présentes dans un PDF ou un ticket sont des données du client, pas des ordres pour l’agent. Les écritures et envois doivent suivre le mandat convenu, avec revue des cas ambigus.

Ces propriétés rendent les résultats intégrables et contrôlables ; elles ne remplacent pas les entretiens commerciaux. Pas besoin d’une plateforme multi-agents pour tester la première tâche.

## Monétisation : du pilote au produit

1. **Prestation assistée** : vendre un résultat et faire tourner la CLI nous-mêmes ; observer les exceptions et facturer le pilote.
2. **Licence pour opérateur ou agence** : plusieurs clients, mêmes règles, intégration CLI/MCP, quotas et dossiers isolés. La distribution par agence peut réduire la prospection client par client, mais exige aussi support et marge revendeur.
3. **Abonnement hébergé** : seulement quand déploiement, coûts et support sont assez standardisés. Abonnement de base + volume de documents/SKU/dossiers ; dépassements visibles et plafonnés.

Éviter la tarification illimitée, les prix fondés uniquement sur les tokens et le pourcentage d’« économies » non attribuables. Un audit ponctuel n’est pas du MRR. Un paiement annuel est un encaissement, pas douze ventes déjà renouvelées.

### Exemple financier explicite : CatalogReady

Hypothèse : 199 €/mois, 500 références maximum, un client déjà configuré. Budget à mesurer : 20 € de traitement/stockage et 1 heure de support/revue valorisée à 30 €. Contribution après ces deux postes : **149 €/client/mois**.

| Comptes actifs | CA mensuel récurrent | Contribution après traitement et 1 h/client | Support/revue mensuel |
|---:|---:|---:|---:|
| 5 | 995 € | 745 € | 5 h |
| 10 | 1 990 € | 1 490 € | 10 h |
| 25 | 4 975 € | 3 725 € | 25 h |

Restent acquisition, développement, frais fixes, incidents, commissions éventuelles et prélèvements. À trois heures par client, la contribution unitaire descend à 89 €. Avec 25 clients, cela représente 75 heures de support/revue avant le reste, incompatible avec un budget de 10–15 h/semaine. **Le risque dominant peut être la revue humaine, pas le coût du modèle.**

Ces volumes sont des scénarios, pas des prévisions ; zéro vente reste possible. Le plafond de 500 références n’est soutenable à ce prix que si la majorité passe des contrôles fiables et si les exceptions sont bornées ou facturées séparément.

## Comment choisir à partir des besoins réels cette semaine

Ne lancer que la découverte commerciale de CatalogReady et FeedRepair, puis retenir un seul pilote.

Pour chaque piste, chercher cinq interlocuteurs qui exécutent déjà la tâche : responsables catalogue et agences Shopping. Les cinq conversations sont un objectif de recherche, pas un taux de conversion attendu. Demander un exemple récent et anonymisable avant toute démonstration générale.

Questions qui départagent les idées :

- Quelle opération précise a été bloquée la dernière fois ?
- Montre-moi les fichiers ou écrans entre lesquels tu as dû naviguer.
- Combien de fois par mois, combien de minutes et combien de personnes ?
- Quel outil paies-tu déjà, et qu’est-ce qui reste manuel malgré lui ?
- Quelle erreur rendrait le résultat inutilisable ? Qui peut le valider ?
- Peux-tu fournir un lot historique avec le résultat correct, et qui peut acheter un pilote au prix proposé ?

Continuer si deux prospects indépendants décrivent le même problème, si les données sont accessibles et si au moins un accepte un pilote payé. Ensuite comparer à **l’outil natif + une procédure simple**, pas seulement au travail totalement manuel.

Écarter une piste si le besoin n’est qu’occasionnel pour l’abonnement envisagé, si l’outil existant le résout déjà, si les autorisations d’accès sont disproportionnées, ou si l’économie de temps disparaît dans les corrections. La prochaine preuve à obtenir est un dossier réel et un premier paiement, pas une nouvelle liste de fonctionnalités.
