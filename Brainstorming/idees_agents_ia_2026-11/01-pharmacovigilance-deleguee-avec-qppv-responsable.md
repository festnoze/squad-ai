# Pharmacovigilance déléguée avec QPPV responsable (C01)

Étude réalisée le 2026-11-03

Statut : rapport final. Verdict **go conditionnel**, valable uniquement pour la version recadrée (section 9.6) ; la version initiale passe en no-go si aucun binôme de QPPV seniors n'entre au capital.

Étiquettes de confiance : [vérifié] = source primaire ou deux sources concordantes ; [estimé] = calcul à partir de données sourcées, méthode indiquée ; [hypothèse] = ordre de grandeur sans source. Les numéros entre crochets renvoient à la section 13.

## 1. Résumé exécutif

**Go conditionnel, sur une version recadrée.** Le besoin est quasi indestructible. Le droit européen impose à tout titulaire d'AMM un QPPV, personne physique qui réside dans l'Union et que l'on déclare à l'EMA, et la France exige en plus un RPV médecin ou pharmacien [52] [53] [vérifié]. Aucun éditeur de modèle ne prendra ce rôle. Pourtant, **la résistance aux LLM de l'idée telle qu'elle est formulée n'est que de 5/10**, pour trois raisons :

- le rôle de QPPV n'est pas exclusif : chaque CRO, chaque boutique et chaque QPPV indépendant le vend déjà ;
- la couche d'agents devient une commodité dès 2027, avec Veeva Falcon Safety (annoncé le 01/09/2026) [18] et Graph AI (13,3 M$ levés) [17] ;
- le créneau du bas prix est déjà occupé : Tepsivo vend une PV complète avec QPPV pour 60 à 100 k€ par an et se dit à environ 30 % du prix de marché [14] [vérifié].

Trois prémisses de la fiche sont fausses :

- les ICSR ne croissent pas de 10 % par an, mais de 0,5 % en 2025 [1] ;
- les génériques et la phytothérapie traditionnelle sont exemptés de PSUR de routine [55] ;
- la mutualisation des données entre génériqueurs reproduit un service public gratuit (EudraVigilance et MLM de l'EMA) [1] [42].

Le marché est petit. Sans croissance externe, C01 deviendra une boutique rentable de 1 à 2 M€ d'ARR, pas une plateforme.

| Indicateur clé | Valeur retenue | Confiance |
|---|---|---|
| Titulaires cibles (10 à 500 salariés) | Environ 140 en France (120 à 180) ; environ 1 100 en Europe | [estimé] |
| Budget de PV actuel adressable | France 17 à 31 M€ ; Europe 165 à 220 M€ ; monde 0,5 à 0,8 Md€ | [estimé] |
| Même périmètre au prix de C01 | France 6 à 11 M€ ; Europe 60 à 80 M€ | [estimé] |
| SOM à la fin de l'année 3 | 15 clients, 0,68 M€ d'ARR (de 0,32 à 1,25 M€) | [estimé] |
| Panier moyen ; marge brute | 45 k€ par an ; 45 à 50 % au départ | [estimé] |
| Coût d'inférence | Environ 1 k€ par client et par an (moins de 3 % du CA) | [estimé] |
| ICSR reçus par EudraVigilance | 1,91 M (2023), 1,76 M (2024), 1,77 M (2025) [1] [2] | [vérifié] |

**Condition de succès numéro un.** Avant toute levée, deux QPPV seniors doivent entrer au capital, l'un comme titulaire et l'autre comme suppléant. Au moins l'un d'eux doit avoir déjà passé des inspections de l'ANSM sans constat critique. Tous deux s'engagent par écrit sur le niveau d'automatisation qu'ils acceptent de signer.

**Pivot recommandé :**

- racheter une boutique française de PV déjà inspectée, ou s'y adosser ;
- se spécialiser sur le « jour 1 » : nouvelle AMM, transfert de portefeuille ou départ du QPPV, avec reprise du PSMF en 30 jours ;
- vendre un engagement de conformité couvert par un assureur ;
- s'étendre ensuite aux micro-titulaires européens par la veille de littérature locale.

## 2. L'idée

### 2.1 Problème et solution

Un titulaire d'AMM de 10 à 500 salariés doit entretenir un système de PV complet, même s'il reçoit peu de cas :

- un QPPV et un suppléant joignables 24 heures sur 24, et un RPV en France ;
- un PSMF et une base de sécurité validée, reliée à EudraVigilance ;
- la veille bibliographique hors MLM, les signaux, les rapports périodiques et la réconciliation des cas avec les partenaires.

Faire tout cela en interne coûte 250 à 340 k€ par an [estimé]. Ce total additionne un QPPV à environ 148 k€ chargés (le salaire de [39] multiplié par 1,45), un suppléant à temps partiel, un chargé de PV, une base de sécurité à 20 à 60 k€ et des audits. Les CRO facturent au temps ou au cas et servent mal les petits comptes. La douleur se mesure : en 2025, seuls 80,4 % des cas non graves ont été transmis dans le délai de 90 jours. Depuis décembre 2025, l'EMA envoie à chaque titulaire un rapport automatique de conformité [1] [vérifié].

C01 vend une PV clé en main au forfait. La société tient le rôle de QPPV : celui-ci est nommé dans le PSMF et déclaré dans la base de l'article 57. Elle tient aussi le rôle de RPV France, le PSMF et une base de sécurité validée selon GAMP 5 et l'Annexe 11. Des agents produisent le travail, et deux seniors médecins ou pharmaciens signent.

### 2.2 Ce que font les agents, étape par étape

| Étape | Travail des agents | Contrôle humain en version 1 |
|---|---|---|
| 1. Réception | Collecte sur tous les canaux (boîte PV, appels, partenaires sous SDEA, réclamations qualité), dédoublonnage, contrôle des 4 critères de validité, horodatage du jour 0 | Relecture de 100 % des « non-cas » pendant 24 mois |
| 2. Traitement | Codage MedDRA, gravité, caractère attendu au regard du RCP, narration, fichier E2B(R3) | Validation de 100 % des cas graves ; contrôle par échantillon des non graves |
| 3. Transmission | Soumission à EudraVigilance (15 jours pour un cas grave, 90 jours pour un non grave), suivi des accusés de réception | Accord humain avant chaque envoi |
| 4. Veille | Criblage hebdomadaire d'Embase, de PubMed et de la littérature locale hors MLM, exclusions motivées | Relecture des inclusions et d'un échantillon d'exclusions |
| 5. Signaux et synthèse | Analyse des extractions EVDAS, brouillons de PSUR quand ils sont exigés, mises à jour du PSMF, réconciliation mensuelle avec les partenaires et avec les rapports de l'EMA | Décisions et signatures du QPPV |

Le QPPV et son suppléant gardent la validation des cas graves, la causalité, la décision sur les signaux, la signature et la défense en inspection : le CIOMS XIV réserve ces jugements aux experts humains [48] [vérifié]. En version 1, C01 achète une base validée (par exemple chez AB Cube, qui se dit trois fois moins cher qu'Oracle et Veeva [29]) au lieu de la construire. Les agents viennent en surcouche et sont validés sur un corpus de référence. Un portail montre au client ses taux de conformité à 15 et à 90 jours. Un kit d'audit est prêt : SOP, dossier de validation des agents aligné sur l'EMA [49], contrat conforme au règlement 2025/1466 [41].

## 3. Pourquoi maintenant

| Date | Événement | Effet |
|---|---|---|
| 30/09/2024 | Document de réflexion de l'EMA sur l'IA [49] [vérifié] | L'IA est acceptée sous supervision humaine |
| 22/07/2025 | Règlement d'exécution 2025/1466, applicable le 12/02/2026 [41] [vérifié] | Sous-traitance et audits encadrés ; fin des notifications isolées de signaux |
| 04/12/2025 | Rapport final du CIOMS XIV [48] [vérifié] | Un référentiel que l'on peut citer en inspection |
| Décembre 2025 | Rapports automatiques de conformité EudraVigilance [1] [vérifié] | Les retards deviennent visibles |
| 2026 | Révision des modules VI et IX des GVP [1] [vérifié] | Chaque titulaire doit réécrire ses procédures |
| 01/10/2026, puis 23/11/2026 | Position du Conseil sur la directive pharmaceutique, puis plénière indicative du Parlement [50] [51] | Application vers 2028-2029 [hypothèse] |
| Novembre 2026 à 2027 | Veeva Falcon Safety, d'abord en accès anticipé puis disponible pour tous [18] | Fin de l'avance technique d'un entrant |

La pression économique pousse aussi à externaliser. Le Leem fait état d'une clause de sauvegarde de 1,6 Md€ sur 2024-2025 et d'une nouvelle baisse de prix de 1 Md€, pour 27 Md€ de chiffre d'affaires [7] [vérifié]. La fiche contient pourtant deux erreurs :

- **Les volumes ne portent pas l'activité** : 1 908 605 ICSR en 2023, 1 757 524 en 2024 (-7,9 %) et 1 765 581 en 2025 (+0,5 %) [1] [2] [vérifié].
- **Le codage MedDRA n'est fiable qu'en partie.** Il atteint 86,7 à 90,2 % d'exactitude sur des termes cliniques [56], mais 35 à 40 % au premier rang sur des verbatims de patients [57] [vérifié]. Une revue de 83 études conclut que seuls des usages supervisés et ciblés sont justifiés [58] [vérifié].

« Maintenant » désigne donc une fenêtre de 18 à 36 mois [hypothèse], pas une vague de fond.

## 4. Marché

### 4.1 Définition et clients cibles

Le périmètre est la PV post-AMM des titulaires de 10 à 500 salariés. La post-AMM représente 76 % de la dépense mondiale de PV [10] [11] [vérifié]. En sont exclues la PV des essais cliniques et la PV des groupes qui la centralisent. Les amendes pèsent peu dans la décision d'achat. En 2025, l'ANSM a prononcé 6 sanctions financières, toutes pour ruptures de stock, pour 754 727 € au total [5] [vérifié]. Entre 2018 et 2022, elle a prononcé 0 à 3 injonctions par an après inspection de PV [4] [vérifié].

| Zone | Méthode | Cibles |
|---|---|---|
| France | 283 exploitants [4] x 50 % ; recoupé par les 173 PME et ETI titulaires d'AMM de prescription [9], plus 80 à 150 laboratoires OTC, de phytothérapie et importateurs [hypothèse] | **Environ 140 (120 à 180)** [estimé] |
| Europe | 1 174 titulaires ont déclaré des cas à EudraVigilance en 2025 [1] ; on retire 25 % de grands groupes et on ajoute 20 à 40 % de titulaires sans cas dans l'année | **Environ 1 100** [estimé], cohérent avec les 1 259 entreprises de la NACE C21 de 10 à 249 salariés [3] |
| Monde | UE, Royaume-Uni, Suisse, États-Unis, Asie | Environ 4 000 [hypothèse] |

Les deux chapitres sources donnent 110 à 170 et 120 à 180 comptes pour la France : nous retenons 140. L'OTC français est concentré, puisque les 24 laboratoires de NèreS en font 80 % [8] [vérifié]. Les petits laboratoires de phytothérapie sont nombreux, mais leurs paniers sont faibles.

### 4.2 TAM, SAM, SOM

| Étape | Monde | Europe | France |
|---|---|---|---|
| Marché de la PV en 2025 | 8,6 Md$ [10] à 10,4 Md$ [11], soit 7,5 à 9,0 Md€ (1 € = 1,15 $) | 2,23 Md$ [11], soit 1,94 Md€ | 271 M€ (14 % de l'Europe, soit la part française de l'emploi de la NACE C21 [3]) |
| Descendant : x 76 % (post-AMM) x part des petits titulaires (12 à 15 % [hypothèse]) | 0,68 à 0,82 Md€ | 220 M€ | 31 M€ |
| Ascendant : titulaires x dépense actuelle (120 à 150 k€ [hypothèse calée sur [14]]) | 0,52 Md€ | 165 M€ | 17 M€ |
| Même parc x panier de C01 (45 à 55 k€) | 0,20 Md€ | 60 M€ | 6,3 M€ |

**TAM retenu, en budget actuel : France 17 à 31 M€, Europe 165 à 220 M€, monde 0,5 à 0,8 Md€** [estimé]. Pour la France, la borne basse est la plus sûre : la méthode descendante y applique une moyenne européenne, alors que l'OTC français est concentré. Au prix de C01, le même périmètre vaut **6 à 11 M€ en France et 60 à 80 M€ en Europe**. La remise réduit donc le marché en valeur, et C01 doit gagner par la marge.

**SAM** [estimé]. En France, 70 titulaires sont prêts à externaliser à la fois le QPPV et le PSMF (140 x 50 % [hypothèse]), soit **3,2 M€** au prix de C01. En Europe francophone et du Sud, l'hypothèse est d'environ 200 titulaires : 1 100 x 36 % [3] x 50 %, soit **11 M€** à partir de l'année 3.

**SOM.** Environ 23 contrats de 3 ans arrivent à échéance chaque année, auxquels s'ajoutent une dizaine de déclencheurs [hypothèse]. Avec un taux de gain de 10 à 15 %, C01 signe 3 à 5 clients par an [estimé].

| Scénario | Clients à la fin de l'année 3 | Panier | ARR |
|---|---|---|---|
| Pessimiste | 8 | 40 k€ | 0,32 M€ |
| **Central** | **15 (dont 3 hors de France)** | **45 k€** | **0,68 M€** |
| Optimiste (ouverture de la Belgique et de la Suisse) | 25 | 50 k€ | 1,25 M€ |

Le chapitre go-to-market vise 10 clients à 24 mois. Au rythme de 3 à 5 signatures par an, nous retenons plutôt **6 à 10 clients à 24 mois**.

### 4.3 Croissance et moteurs

- **Taux de croissance.** Le marché mondial de la PV croît de 5,6 à 8,9 % par an [10] [11] et le marché européen de 7,5 % [11]. L'externalisation progresse de 15,1 % par an et représente 60 % de la dépense [12] [11] [vérifié, chaque chiffre repose sur une source unique d'institut].
- **Moteurs.** Les obligations fixes s'accumulent : GVP révisées, règlement 2025/1466, conformité désormais visible. La rareté des QPPV pousse aussi à externaliser : au moins 3 postes étaient ouverts sur France Travail à Paris et à Lyon en novembre 2026 [40] [vérifié]. Enfin, le dictionnaire XEVMPD est passé à 1 434 187 entrées (+26 % en 2025), avant sa bascule vers le PMS prévue après 2028 [1] [vérifié].
- **Conséquence.** La facturation doit suivre le périmètre couvert et non le nombre de cas, puisque les volumes stagnent.
- **Adjacences.** La première est la PV des essais cliniques : 690 promoteurs ont déclaré à l'EVCTM en 2025 [1]. Suivent le QPPV au Royaume-Uni et en Suisse, puis la PV vétérinaire. La vigilance des dispositifs médicaux (rôle de PRRC) recoupe C03 et doit être arbitrée à l'échelle du portefeuille.

## 5. Clients et segments

### 5.1 ICP et personas

| Segment | Profil | Déclencheur | Cas par an [hypothèse] | Priorité |
|---|---|---|---|---|
| OTC et phytothérapie | 10 à 100 salariés, 3 à 15 substances anciennes | Départ du QPPV, fin de contrat CRO | 20 à 150 | 1 |
| Génériqueurs et importateurs parallèles | 20 à 500 salariés, 20 à 200 AMM | Rachat de portefeuille, constat d'inspection | 100 à 1 000 | 1 |
| Biotech en lancement | 1 ou 2 substances nouvelles | Nouvelle AMM | 50 à 500 | 2 |
| Exploitants pour compte de tiers | AMM de titulaires étrangers | Nouveaux mandats | Variable | Canal |

Les segments prioritaires sont exemptés de PSUR de routine [55]. La valeur des agents y porte donc sur la réception, la veille locale, le PSMF et la réconciliation. Les PSUR concernent surtout les biotechs.

| Persona | Douleur quantifiée | Ce qu'il achète |
|---|---|---|
| **Décideur** : pharmacien responsable, directeur général ou réglementaire | Un QPPV coûte 102 k€ brut en Île-de-France (75 à 150 k€) [39], 85 à 95 k€ pour un poste senior à Paris [40], soit environ 148 k€ chargés [estimé]. Une vacance de poste rend le titulaire immédiatement non conforme | Un nom dans le PSMF dès le premier jour, un suppléant |
| **Utilisateur** : responsable ou chargé de PV | Environ 90 minutes par ICSR traité à la main [38] [hypothèse], soit 450 heures par an pour 300 cas [estimé]. Veille obligatoire pour toute substance hors des 309 + 100 groupes du MLM [42] | Des délais tenus, moins de saisie |
| **Bloqueurs** : assurance qualité, DPO, prestataire en place | Un constat critique imputable au fournisseur ; jusqu'à 150 000 € d'amende pénale pour défaut de déclaration [43] [vérifié] | Validation, audit trail, réversibilité |

Pour le client, l'offre est rentable dès le premier produit : 24 à 108 k€ par an chez C01, contre 250 à 340 k€ en interne [estimé]. NextPV estime l'équipe interne d'une biotech à 300 à 500 k€ [33] [vérifié, source intéressée]. Le risque est surtout réputationnel : C01 vend la tranquillité en inspection, pas l'évitement d'une amende.

### 5.2 Processus d'achat

| Déclencheur | Urgence | Cycle [hypothèse] |
|---|---|---|
| Départ du QPPV interne | Forte | 1 à 3 mois |
| Nouvelle AMM ou rachat de portefeuille | Forte | 2 à 4 mois |
| Constat d'inspection | Moyenne | 3 à 6 mois |
| Renouvellement du contrat CRO | Faible | 6 à 12 mois (appel d'offres, migration validée) |

L'offre se paie sur le budget des affaires pharmaceutiques ou de la qualité, à la place d'un contrat CRO ou d'un salaire. Trois fonctions valident l'achat :

- l'assurance qualité, après un audit fournisseur de 1 à 3 jours [hypothèse] ;
- le DPO, au titre de l'article 28 du RGPD ;
- la direction financière, qui s'engage sur 3 ans.

Prérequis avant toute vente : un contrat conforme au règlement 2025/1466, où les sous-traitants ultérieurs, dont l'hébergeur et le fournisseur de modèles, sont autorisés par écrit [41] [vérifié], ainsi qu'un hébergement HDS dans l'EEE.

## 6. Concurrence

### 6.1 Acteurs en place

| Acteur | Offre | Mouvements datés |
|---|---|---|
| PrimeVigilance (Ergomed, groupe racheté par Permira) | PV complète, QPPV, PSMF | Rachat d'Ergomed en 2023 pour environ 700 M£ [hypothèse, presse non revérifiée] ; migration vers Oracle Argus Cloud le 08/07/2025 [22] |
| PharmaLex (Cencora) | ICSR, veille, signaux, QPPV | Rachat finalisé le 03/01/2023 [25] |
| IQVIA | Plateforme Vigilance, QPPV européen externalisé | IQVIA.ai et plus de 150 agents (16/03/2026) [23] |
| Biomapas (Carbyne Equity) | PV complète, QPPV | Rachats de Delta PV (04/08/2025) et de Pinnaxis (2026) [26] |
| Qinecsa (Stanley Capital) | Services outillés | Rachat d'Insife (21/03/2024) [27] |
| ProductLife Group (Paris) | Réglementaire et PV | Rachat de Stragen Services (Lyon, 28/01/2025) [28] |
| Excelya, Pharmya, Atessia, Arriello, Insuvia, NextPV, DDReg | QPPV, RPV ou LPPV, PSMF | Seul NextPV met l'IA en avant [32] [33] |

| Éditeur ou startup | Produit | Fait daté |
|---|---|---|
| Veeva | Falcon Safety | Annoncé le 01/09/2026 ; compatible Argus et LifeSphere ; premiers clients en novembre 2026 [18] ; agents dans toutes les applications Vault depuis le 14/10/2025 [19] |
| ArisGlobal | NavaX | Codage MedDRA automatisé à plus de 80 %, chez 7 grands laboratoires (29/07/2025) [20] |
| Oracle | Argus, Safety One Intake | Réception des cas par IA (10/07/2024) [21] |
| AB Cube (Paris) | SafetyEasy | 475 clients revendiqués [29] |
| **Tepsivo** (Finlande, 2020) | PV complète avec QPPV européen, au forfait | Plus de 50 clients ; 60 à 100 k€ par an pour 1 à 10 marchés ; 600 € par mois et par pays pour un contact local [14] ; Clinigen actionnaire minoritaire depuis le 27/01/2025 [15] |
| Graph AI (États-Unis, 2024) | Logiciel de PV natif IA | 3 M$ (15/10/2025) [16], puis 13,3 M$ (10/09/2026) [17] ; un cas traité en moins de 10 minutes au lieu de plus de 3 heures (selon l'éditeur) |
| Biologit, Synapse Medicine | Veille bibliographique ; codage MedDRA | 2,1 M$ levés le 14/02/2025 [30] ; déploiement dans les CRPV avec l'ANSM pendant la vaccination Covid [31] |

La consolidation sous capital-investissement rend marginaux les comptes de 18 à 72 k€ par an. Les startups financées vendent du logiciel et n'assument pas la responsabilité réglementaire. **Tepsivo est le seul concurrent direct** qui combine agents, QPPV et forfait. Des paliers d'entrée à 500 et 1 000 € par mois sont évoqués, sans confirmation [hypothèse].

### 6.2 Grands acteurs et substituts

Les grands acteurs de l'IA ont **moins de 5 % de chances** de couvrir le besoin [hypothèse] :

- **OpenAI** : partenariat avec Novo Nordisk et rachat d'Orchestra Bio le 20/10/2026, deux opérations centrées sur la R&D [35] ;
- **Anthropic** : Claude for Healthcare (11/01/2026) avec des connecteurs PubMed. Ce sont des briques que tous les concurrents pourront utiliser [34] ;
- **Salesforce** : capture des effets indésirables déclarés par les patients [36] ;
- **Google, Microsoft, SAP et ServiceNow** : aucune offre de PV.

Le vrai risque vient des **éditeurs métiers** (Veeva, Oracle, ArisGlobal, AB Cube) qui vendent leurs agents aux cabinets déjà en place. L'assistant Elsa de la FDA résumerait des effets indésirables avec Claude [37] [hypothèse, source secondaire unique] : l'automatisation se légitime, mais la responsabilité ne se transfère pas.

| Substitut | Coût | Limite |
|---|---|---|
| PV interne aidée par ChatGPT ou Copilot | 300 à 500 k€ par an [33] | Ni QPPV, ni base validée ; un LLM non validé crée un risque d'inspection |
| CRO ou boutique classique | 30 à 80 k€ pour un petit titulaire français [hypothèse] ; 210 à 400 k€ pour une biotech [estimé d'après [33]] | Facturation au temps, peu d'attention aux petits comptes |
| **QPPV indépendant et logiciel IA** | 1 000 à 3 000 € par mois, plus une licence [hypothèse] | Dépend d'une seule personne, suppléance fragile |
| Statu quo | Coût d'une migration validée | Cède à un déclencheur |

Le substitut le plus dangereux est **le QPPV indépendant équipé d'un logiciel IA** : il a la même structure de coûts que C01.

### 6.3 Positionnement et intensité

| | Responsabilité faible (logiciel) | Responsabilité forte (QPPV nommé, PSMF tenu) |
|---|---|---|
| Agents natifs | Graph AI, Veeva Falcon, NavaX, Safety One, SafetyEasy, Biologit, Synapse | Tepsivo (UE, généraliste) ; **espace de C01 : France, petits titulaires, génériques, phytothérapie, OTC** |
| Travail facturé au temps | BPO, prestataires de codage | PrimeVigilance, Cencora, IQVIA, Biomapas, Qinecsa, PLG, boutiques françaises |

L'espace de C01 est trop petit pour les grands, trop réglementé pour les éditeurs, trop local pour les généralistes européens (RPV, littérature francophone, ANSM) et trop risqué sans QPPV. Il se refermera par le bas : les boutiques françaises adopteront les agents des éditeurs dès 2027, et Tepsivo peut ouvrir un RPV français. **Intensité concurrentielle : 6/10.**

## 7. Modèle économique et prix

### 7.1 Modèle et repères

Le modèle retenu est un **abonnement indexé sur le périmètre** (substances, pays, cas inclus), assorti d'un SLA avec avoirs et de frais de mise en place. Le paiement au temps est exclu, car chaque gain de l'IA y réduit le chiffre d'affaires. Le paiement au cas l'est aussi : il banalise l'offre, et les volumes stagnent.

| Repère | Prix | Confiance |
|---|---|---|
| Tepsivo, petite structure / plus de 20 marchés | 60 à 100 k€ / 200 à 350 k€ par an [14] | [vérifié] |
| Prix de marché implicite pour une petite structure | 200 à 330 k€ par an (le prix Tepsivo divisé par 0,30) | [estimé] |
| Licence de logiciel de PV | 60 à 300 k€ par an [14] | [vérifié] |
| Cabinets français, petits titulaires | 30 à 80 k€ par an | [hypothèse] |

Arbitrage : la remise de 40 à 60 % est réelle face aux CRO classiques. Face à Tepsivo et aux boutiques françaises, la grille de C01 se situe en revanche dans la même zone de prix. **Le prix est une condition d'entrée, pas un avantage.** C01 doit donc vendre un QPPV francophone qui est aussi RPV, l'expérience des inspections de l'ANSM et un SLA de conformité.

### 7.2 Grille recommandée [hypothèse]

| Offre | Périmètre | Prix |
|---|---|---|
| Essentiel | 5 substances, 100 cas par an, France | 2 000 € par mois ; 40 € par cas non grave et 150 € par cas grave au-delà |
| Standard | 15 substances, 400 cas, France et 2 pays | 3 500 € par mois ; 500 € par pays supplémentaire |
| Lancement | 1 ou 2 substances nouvelles, PSUR semestriel | 6 000 à 9 000 € par mois |
| Jour 1 (offre du pivot) | Reprise du PSMF, migration et réconciliation en 30 jours | 15 à 40 k€ une fois, puis l'une des offres ci-dessus |
| Mise en place standard | Migration validée, PSMF | 10 à 25 k€ une fois |
| SLA | 100 % des cas graves à 15 jours, au moins 98 % des non graves à 90 jours | Avoir de 10 % du forfait pour chaque mois hors cible |

Le plancher passe de 1 500 € à 2 000 € par mois : en dessous, la marge d'un client Essentiel tombe sous 40 % [estimé].

### 7.3 Unit economics

Avec une répartition de 40 % d'Essentiel, 45 % de Standard et 15 % de Lancement, et une part variable d'environ 10 %, le panier atteint **45 k€ par an** [estimé]. Coût de service annuel d'un client Standard (300 cas, 10 substances hors MLM) :

- **inférence** : environ 1 k€ [estimé]. Le calcul retient 0,8 $ par cas (150 000 jetons en entrée et 12 000 en sortie sur Sonnet 5.5, relecture des cas graves sur Opus 5.5 [44]), auxquels s'ajoutent la veille et les PSUR, puis un doublement pour couvrir les tests ;
- **heures humaines** : environ 13 k€ [estimé], soit 200 heures à 65 € ;
- **base, hébergement HDS, MedDRA, Embase** : 5 à 7 k€ [hypothèse] ;
- **qualité et assurance** : 2 à 3 k€ [hypothèse] ;
- **total : 21 à 24 k€.**

| Indicateur | Valeur | Confiance |
|---|---|---|
| Marge brute | 45 à 50 % au départ ; 65 à 70 % visés à 100 clients | [estimé] |
| CAC | 25 à 30 k€ (un commercial, 40 k€ d'événements, 6 signatures par an) | [estimé] |
| Récupération du CAC | 12 à 16 mois | [estimé] |
| Clients perdus par an | 5 à 8 %, surtout quand le client est racheté | [hypothèse] |
| LTV / CAC | Environ 6 (45 k€ x 55 % x 7 ans = 170 k€) | [estimé] |

### 7.4 La thèse « le progrès des modèles devient de la marge »

L'inférence pèse moins de 3 % du chiffre d'affaires : un modèle dix fois moins cher n'y change presque rien. Le vrai levier est le nombre d'heures humaines, qu'un meilleur modèle peut réduire, mais à deux conditions :

- **des revalidations peu coûteuses.** Dans un système GAMP 5, changer de modèle impose une revalidation, alors que les modèles changent tous les 3 à 6 mois [hypothèse] ;
- **des concurrents qui ne baissent pas leurs prix** grâce à leurs propres gains. Sur un marché dense, cela tient 12 à 18 mois [hypothèse].

**Arbitrage : la thèse est vraie à court terme et fausse à moyen terme.**

Les chapitres divergent sur la capacité d'un binôme de QPPV : 15 à 25 portefeuilles, 20 à 25 clients ou 15 clients par QPPV. Nous retenons **15 à 20 clients par binôme pendant les trois premières années**, car ce ratio sera examiné en inspection. Deux QPPV portent donc 30 à 40 clients, soit **1,1 à 1,8 M€ d'ARR au plus** [estimé : de 30 clients à 36 k€ jusqu'à 40 clients à 45 k€].

## 8. Go-to-market

**Canaux**, par ordre de priorité :

1. La vente directe par le réseau du QPPV cofondateur : le client achète la confiance qu'il accorde à une personne.
2. Les fédérations : AMLIS, NèreS, GEMME, France Biotech, AFAR.
3. Le suivi des déclencheurs : décisions et transferts d'AMM, offres d'emploi de QPPV [40].
4. Les cabinets réglementaires sans offre de PV, rémunérés par une commission de 10 % [hypothèse].
5. Les exploitants pour compte de tiers, comme Movianto [45], et les conseils en fusions-acquisitions.

| Période | 10 premiers clients | Preuve produite |
|---|---|---|
| Mois 0 à 6 | Licence d'une base validée, environ 40 SOP, hébergement HDS, RC professionnelle, audit blanc par un ancien inspecteur | Rapport d'audit indépendant |
| Mois 4 à 9 | 2 pilotes : traitement en double des cas pendant 60 à 90 jours, gratuit ou à moitié prix | Codage MedDRA conforme, délais, heures par cas |
| Mois 9 à 12 | Premier contrat de 3 ans, avec un laboratoire OTC ou un génériqueur dont le QPPV part | Contrat signé |
| Mois 12 à 24 | Ciblage de 300 comptes ; mise en place offerte aux 5 premiers clients en échange d'une référence | 6 à 10 clients, 0,27 à 0,45 M€ d'ARR [estimé] |

**Les 100 premiers clients (années 3 à 6).** L'expansion passe d'abord par la Belgique et le Luxembourg, puis par l'Espagne, l'Italie et l'Allemagne avec des QPPV locaux. À 100 clients, C01 réaliserait environ 4,5 M€ d'ARR avec 4 à 5 QPPV et 25 à 30 salariés [estimé]. La croissance organique ne suffit pas : racheter un ou deux cabinets français apporte des clients, des QPPV et un historique d'inspection.

**Preuves à réunir :**

- un audit blanc sans constat critique au mois 6 ;
- des taux de conformité supérieurs à la moyenne des titulaires (96,9 % des cas graves à 15 jours, 80,4 % des non graves à 90 jours [1]) ;
- un dossier de validation des agents aligné sur l'EMA et le CIOMS XIV ;
- deux études de cas chiffrées ;
- une première inspection de l'ANSM sans constat critique. Elle est imprévisible : la MHRA n'a mené que 17 inspections en 2022/2023, dont 4 avec constat critique [60] [vérifié, source secondaire].

## 9. Moat et résistance à la montée en puissance des LLM

### 9.1 Actifs revendiqués

| Actif | Réel ? | Contournable par |
|---|---|---|
| Rôle de QPPV nommé (PSMF, base de l'article 57) | Réel face aux éditeurs de modèles, mais pas exclusif. Le titulaire garde l'entière responsabilité de son système, même sous-traité [54] [61] | CRO, boutiques, QPPV indépendants, Tepsivo [14] [32] |
| RPV France | Petite barrière face aux acteurs étrangers [53] | Tepsivo (contact local à 600 € par mois [14]) |
| Base validée et historique des cas | Réel : la migration crée un coût de sortie (6 à 12 mois de validation [hypothèse]) | Export E2B(R3) standard ; les agents réduiront eux-mêmes le coût des migrations |
| Données mutualisées par substance | Largement illusoire : les cas appartiennent à chaque titulaire (contrats, article 9 du RGPD). EudraVigilance compte déjà 31,2 millions d'ICSR [1] | L'EMA, gratuitement (MLM [42]) |
| Détection de signaux propriétaire | Faible. L'EMA a examiné 1 201 signaux potentiels en 2025. Sur 61 signaux notifiés par des titulaires entre 2018 et 2025, 1 seul a été confirmé, et ces notifications ont été supprimées [1] [vérifié] | Le régulateur |
| Historique d'inspections | Réel, mais il profite aux acteurs installés (3 à 6 ans pour le constituer [hypothèse]) | Personne, sauf à l'acheter |
| Pile d'agents ; effets de réseau | Non durable (environ 6 mois d'avance [hypothèse]) ; aucun effet de réseau, car les données sont cloisonnées | Veeva, IQVIA, Graph AI, Tech Mahindra [18] [24] [17] |

Les actifs propres à l'entrant sont les plus faibles. Le seul actif fort, la signature du QPPV, appartient à une personne qui peut partir.

### 9.2 Scénarios

| Scénario | Effet | Qui capte la marge |
|---|---|---|
| Modèles 2x meilleurs (2027) | Les cas déclarés par des professionnels passent presque sans retouche ; les CRO adoptent Falcon ou Graph AI ; guerre des prix | L'entrant pendant 12 à 18 mois, puis l'éditeur et le client |
| Modèles 10x, pilotage fiable des interfaces (2028-2029) | Un agent pilote EVWEB, le portail de l'ANSM et la boîte PV. Un micro-titulaire assemble lui-même une base SaaS, un agent et un QPPV indépendant à la journée | Les éditeurs (logiciel) et les QPPV rares ; l'intermédiaire est pris en étau |
| Agents natifs des plateformes | Les plateformes de la verticale sont Veeva Vault, Argus et LifeSphere, pas SAP ni Salesforce ; Veeva livre déjà la réception et la narration [18]. Copilot ou Gemini trient la boîte PV, sans offrir de base validée | Veeva et ses CRO partenaires |
| Modèles ouverts au niveau de la frontière | Inférence quasi gratuite, hébergeable en France ; les modèles ouverts ont 5 à 22 mois de retard [59] | Ceux qui ont déjà les clients : les acteurs installés |

### 9.3 Tests de résistance

| Test | Résultat |
|---|---|
| ChatGPT et un stagiaire font-ils 80 % du travail ? | **Réussi** : il manque le QPPV déclaré, le système inspectable et la disponibilité 24 heures sur 24 |
| Assistant IA, QPPV indépendant 2 jours par mois et base SaaS | **Échoué** pour 1 à 5 produits : environ 1 500 € par mois [hypothèse] |
| Un acteur installé reproduit-il l'offre en 12 mois ? | **Échoué** : il achète Falcon et possède déjà QPPV, clients et historique |
| Le prix tient-il quand les coûts baissent ? | **Échoué** à moyen terme [14] |
| Un QPPV peut-il signer pour des dizaines de titulaires automatisés ? | **Incertain** : l'EMA exige une approche centrée sur l'humain [49] ; le CIOMS XIV met en garde contre une automatisation guidée par la finance [48] |
| Les volumes portent-ils la croissance ? | **Échoué** : +0,5 % ; cas non graves -5 % ; déclarations de patients -11 % [1] |

**Note de résistance aux LLM : 5/10.** Le besoin est quasi indestructible (8/10), mais la position de l'entrant est fragile (3/10). L'idée survit au stagiaire équipé de ChatGPT, pas à un concurrent humain équipé des mêmes modèles.

### 9.4 Ce qui tuerait l'idée, et les contre-mesures

| Scénario de mort | Mécanisme | Contre-mesure |
|---|---|---|
| Constat critique systémique | Un agent classe en « non-cas » une catégorie entière de messages (réclamations qualité, messages en langue étrangère). Le défaut touche tous les clients à la fois : le risque est corrélé | Relecture de 100 % des « non-cas » pendant 24 mois ; dans le doute, traiter le message comme un cas ; réconciliation avec les rapports de l'EMA ; tests de non-régression à chaque changement de modèle ; RC professionnelle couvrant le pire scénario |
| Compression des prix | Falcon devient disponible pour tous, les boutiques s'outillent, et la remise devient le prix de marché. Deux QPPV plafonnent alors à environ 1,1 M€ d'ARR [estimé : 2 x 15 clients x 3 000 € x 12 mois] | Niches que les acteurs installés délaissent ; engagement de résultat ; QPPV associés au capital |
| Départ de la personne clé | Le QPPV part ou refuse de signer. Les clients mettent à jour leur PSMF et repartent vers un acteur installé | Deux QPPV dès le départ ; pacte d'associés ; charte d'automatisation ; assurance homme-clé |
| Coût de revalidation | Chaque nouveau modèle déclenche une revalidation | Modèle figé à chaque version validée ; corpus automatisé ; au plus deux changements par an |

### 9.5 Version la plus résistante (pivot)

1. **Abandonner trois arguments** : la mutualisation des données, les signaux propriétaires et la croissance des volumes.
2. **Acheter l'historique** : racheter une boutique française de 10 à 30 clients, avec un QPPV qui a déjà traversé des inspections, ou s'y adosser, puis y greffer les agents.
3. **Se spécialiser sur le jour 1** : nouvelles AMM, transferts de portefeuille, départs de QPPV. Les LLM accélèrent vraiment la reprise de données sales et multilingues, et l'urgence du client écrase la sensibilité au prix.
4. **Vendre un engagement de conformité assuré** : des pénalités adossées à un assureur, qu'un prestataire payé au temps ne peut pas suivre.
5. **Viser les micro-titulaires européens** avec une veille de la littérature locale hors MLM dans les langues de l'Union [42].

Ainsi recadrée, l'idée atteint **6 à 7/10** : la signature reste le produit, l'IA devient la structure de coûts, et l'actif défendable est une réputation d'inspection, achetée avec la boutique.

## 10. Réglementation et risques

| Cadre | Ce qui s'applique | Conséquence |
|---|---|---|
| **AI Act** | Usage absent de l'Annexe III, logiciel sans finalité médicale : pas de haut risque [hypothèse]. Maîtrise de l'IA (article 4) exigée depuis le 02/02/2025 ; obligations des fournisseurs de modèles depuis le 02/08/2025. L'Omnibus IA (27/07/2026) reporte l'Annexe III au 02/12/2027 et l'Annexe I au 02/08/2028 [46] [vérifié] | Charge faible ; un agent conversationnel doit annoncer qu'il est une IA |
| Directive 2001/83/CE, règlement 520/2012 modifié par le 2025/1466 | QPPV résidant dans l'UE ; contrats et audits des sous-traitants ; exploitation d'EudraVigilance, applicable depuis le 12/02/2026 [41] [52] [vérifié] | Contrat type et dossier d'audit prêts avant la vente |
| Code de la santé publique | RPV en France [53] ; sanctions de l'ANSM proportionnées au chiffre d'affaires (article L.5471-1) [6] | Le QPPV cofondateur doit pouvoir être RPV |
| Validation informatisée | GAMP 5, Annexe 11, Part 11. Le projet d'Annexe 22 (2025) écarterait les modèles génératifs des usages critiques en BPF [hypothèse] | Revalidation à chaque changement de modèle |
| RGPD et HDS | C01 est sous-traitant (article 28) de données de santé (article 9) ; analyse d'impact obligatoire. Le référentiel HDS v2 (arrêté du 26/04/2024) impose un stockage dans l'EEE [47] | Inférence dans l'UE sans conservation, pseudonymisation, hébergeur HDS |
| Responsabilité | Le titulaire reste responsable même s'il délègue [54] [61] [vérifié] | Responsabilité plafonnée à 1 ou 2 ans d'honoraires ; RC professionnelle de 2 à 5 M€ [hypothèse] |

| Risque | Probabilité | Impact |
|---|---|---|
| Aucun binôme de QPPV seniors prêt à engager son nom | Élevée | Critique |
| Compression des prix (Falcon, boutiques outillées, Tepsivo) | Élevée | Élevé |
| Tepsivo ou une boutique outillée lance une offre française complète | Moyenne à élevée | Élevé |
| Cycle de vente allongé par la migration validée | Élevée | Moyen |
| Constat critique systémique imputable à un agent | Faible à moyenne | Critique |
| Départ du QPPV clé | Moyenne | Critique |
| Ratio de clients par QPPV contesté en inspection | Moyenne | Élevé |
| Revalidation coûteuse, ou logique de l'Annexe 22 étendue aux GVP | Moyenne | Élevé |
| Transfert de données hors UE contesté | Faible | Élevé |

## 11. Feuille de route sur 18 mois

**Équipe :**

- 2 QPPV cofondateurs (titulaire et suppléant), dont l'un est RPV ;
- 1 cofondateur ingénieur, chargé des agents et de la validation ;
- 1 scientifique PV à partir du mois 4 ;
- 1 commercial à partir du mois 9 ;
- en externe : un consultant en validation et un ancien inspecteur pour l'audit blanc.

**Capital** [estimé, sauf mention contraire] :

| Poste | Montant sur 18 mois |
|---|---|
| 2 QPPV (148 k€ chargés x 1,5 an x 70 %, contre des parts au capital) | 310 k€ |
| Ingénieur (100 k€ chargés [hypothèse] x 1,5 an) | 150 k€ |
| Scientifique PV (45 € x 1 450 heures x 1,15 an) | 75 k€ |
| Commercial (110 k€ chargés x 0,75 an) | 85 k€ |
| Base validée, HDS, MedDRA, Embase [hypothèse] | 115 k€ |
| Validation, audit blanc, assurances, juridique, événements [hypothèse] | 160 à 190 k€ |
| **Total, avec 15 % d'imprévus** | **1,0 à 1,2 M€** |

Le revenu cumulé à 18 mois reste de 0,1 à 0,15 M€. Il faut donc lever 1,0 à 1,5 M€ en amorçage, plus des aides de Bpifrance [hypothèse]. La version recadrée ajoute le rachat d'une boutique, valorisée 0,8 à 1,5 fois son chiffre d'affaires [hypothèse]. Le besoin total passe alors à **2,5 à 4 M€**, dette d'acquisition comprise [hypothèse].

| Période | Jalons | Critère d'arrêt |
|---|---|---|
| Mois 0 à 3 | Binôme de QPPV signé (pacte, parts, charte d'automatisation) ; base de sécurité choisie ; contrat type conforme au 2025/1466 ; levée de fonds | Pas de binôme au mois 3 : arrêt |
| Mois 3 à 6 | SOP, validation de la base et des agents, hébergement HDS, corpus de référence, audit blanc | Constat critique non levé en 60 jours : arrêt |
| Mois 4 à 9 | 2 pilotes ; 300 comptes ciblés ; premiers échanges avec 2 ou 3 boutiques à racheter | |
| Mois 9 à 12 | Premier contrat de 3 ans | Aucun contrat au mois 12 : arrêt ou adossement |
| Mois 12 à 18 | 4 à 6 clients, 0,18 à 0,27 M€ d'ARR [estimé] ; première mission « jour 1 » ; une revalidation de modèle réelle ; décision de rachat (lettre d'intention ou abandon motivé) | |

**Métriques suivies :**

- **Délais** : 100 % des cas graves transmis à 15 jours, au moins 98 % des non graves à 90 jours (moyennes des titulaires : 96,9 % et 80,4 % [1]).
- **Sécurité** : aucun cas grave classé à tort en « non-cas ».
- **Automatisation** : 70 % des cas non graves validés sans retouche au mois 12, 85 % au mois 18 [hypothèse].
- **Charge** : de 200 à 150 heures humaines par client Standard ; au plus 20 clients par binôme de QPPV.
- **Économie** : marge brute d'au moins 45 % ; revalidation d'un modèle en moins de 4 semaines, pour moins de 15 k€ [hypothèse].

## 12. Scorecard et verdict

| Critère | Note sur 10 | Justification |
|---|---|---|
| Attractivité du marché | 4 | Environ 140 comptes en France ; SAM France de 3,2 M€ au prix de C01 ; volumes stables. La croissance vient de l'externalisation et des obligations fixes |
| Résistance aux LLM | 5 | Besoin indestructible (8), position de l'entrant fragile (3) ; 6 à 7 dans la version recadrée |
| Espace concurrentiel | 4 | Intensité de 6/10 ; Tepsivo occupe déjà le créneau ; les agents des éditeurs équiperont toutes les boutiques |
| Faisabilité | 5 | Technique accessible, mais dépendance à un binôme de QPPV rare ; 6 à 12 mois de validation ; première inspection imprévisible |
| Risque réglementaire inversé (10 = aucun risque) | 4 | AI Act léger, mais responsabilité nominative, inspections, revalidations, Annexe 22 en projet |
| **Globale** | **4,5** | Moyenne arrondie au demi-point ; environ 6 dans la version recadrée |

**Verdict : go conditionnel**, uniquement dans la version recadrée et si cinq conditions sont réunies :

1. Un binôme de QPPV seniors entre au capital avant la levée, et au moins l'un d'eux a l'expérience des inspections de l'ANSM. Sinon, no-go.
2. Le positionnement passe du bas prix au « jour 1 » et à l'engagement de conformité assuré, et les trois arguments réfutés quittent le discours.
3. Un rachat ou un adossement est décidé au plus tard au mois 18, avec un financement de 2,5 à 4 M€.
4. Les preuves arrivent dans les délais : audit blanc au mois 6, pilotes chiffrés au mois 9, premier contrat au mois 12.
5. Un arbitrage de portefeuille est rendu avec C03 (PRRC), qui mobilise des profils tout aussi rares.

Ambition réaliste : une boutique rentable de 1 à 2 M€ d'ARR, ou un consolidateur français de 4 à 5 M€ d'ARR en 5 à 6 ans.

## 13. Sources

Sauf mention contraire, toutes les pages ont été consultées le 2026-11-03.

1. EMA, *2025 Annual Report on EudraVigilance* (EMA/371010/2025), publié le 12/03/2026 : https://www.ema.europa.eu/en/documents/report/2025-annual-report-eudravigilance-european-parliament-council-commission_en.pdf
2. EMA, *2024 Annual Report on EudraVigilance* (EMA/559856/2024), publié le 20/03/2025 : https://www.ema.europa.eu/en/documents/report/2024-annual-report-eudravigilance-european-parliament-council-commission_en.pdf
3. Eurostat, statistiques d'entreprises par taille (sbs_sc_ovw), NACE C21, 2021-2024, mise à jour du 30/09/2026 : https://ec.europa.eu/eurostat/databrowser/view/sbs_sc_ovw/default/table
4. ANSM, rapport d'activité 2022, partie Inspection : https://ansm.sante.fr/uploads/2023/10/03/20231005-ra-2022-partie-3-l-inspection.pdf
5. ANSM, rapport d'activité 2025 (juillet 2026) : https://ansm.sante.fr/uploads/2026/07/08/20260708-ansm-ra-2025-2.pdf
6. ANSM, lignes directrices sur les sanctions financières, 08/08/2022 : https://ansm.sante.fr/actualites/ruptures-de-stock-de-medicaments-lansm-actualise-ses-lignes-directrices-relatives-aux-sanctions-financieres
7. Assemblée nationale, MECSS, audition du Leem, mars 2025 : https://questions.assemblee-nationale.fr/dyn/17/comptes-rendus/mecss/l17mecss2425003_compte-rendu.pdf
8. NèreS, *Qui est NèreS* : https://neres.fr/a-propos/qui-est-neres/
9. AMLIS, *Panorama 2024 des PME et ETI du médicament*, 24/09/2024 : https://www.amlis.fr/wp-content/uploads/2024/10/Panorama-PME-Sante-2024.pdf
10. Grand View Research, *Pharmacovigilance Market Report*, juin 2026 : https://www.grandviewresearch.com/industry-analysis/pharmacovigilance-industry
11. Precedence Research, communiqué du 18/02/2025 : https://www.biospace.com/press-releases/pharmacovigilance-market-size-to-worth-22-25-bn-by-2034-says-precedence-research ; données Europe : https://www.precedenceresearch.com/databook/europe-pharmacovigilance-market
12. Research Nester, *Pharmacovigilance Outsourcing Market* : https://www.researchnester.com/reports/pharmacovigilance-outsourcing-market/7363
13. Mordor Intelligence, *Pharmacovigilance Automation Market*, 2026 : https://www.mordorintelligence.ar/industry-reports/pharmacovigilance-automation-market
14. Tepsivo, page tarifs : https://www.tepsivo.com/pricing/ ; article du 28/02/2025 : https://www.tepsivo.com/blog/2025-is-the-year-of-ai-in-pharmacovigilance/
15. Clinigen et Tepsivo, 27/01/2025 : https://www.clinigengroup.com/news/news-container/2025/clinigen-announces-strategic-partnership-with-tepsivo/
16. Graph AI, tour d'amorçage, 15/10/2025 : https://www.prnewswire.com/news-releases/ai-firm-graph-raises-3-million-in-seed-funding-from-bessemer-venture-partners-to-disrupt-8-billion-pharmacovigilance-market-302585070.html
17. Graph AI, série A, 10/09/2026 : https://www.prnewswire.com/news-releases/graph-ai-raises-13-3m-series-a-to-scale-the-first-ai-native-operating-system-for-patient-safety-302874459.html
18. Veeva Falcon Safety, 01/09/2026 : https://www.veeva.com/resources/veeva-falcon-safety-to-work-with-all-e2b-compliant-safety-systems-across-any-intake-channels/ ; https://trial.medpath.com/news/veeva-falcon-safety-automates-adverse-event-intake-across-e2b-compliant-systems
19. Veeva AI, 14/10/2025 : https://www.pharmavoice.com/press-release/20251014-veeva-ai-agents-to-be-released-across-all-veeva-applications/
20. ArisGlobal, premier semestre 2025, 29/07/2025 : https://kyodonewsprwire.jp/index.php/release/202507292895
21. Oracle, Argus et Safety One Intake, 10/07/2024 : https://www.oracle.com/news/announcement/oracle-advances-safety-case-management-for-life-science-organizations-2024-07-10
22. PrimeVigilance et Oracle Argus, 08/07/2025 : https://www.nasdaq.com/press-release/primevigilance-enhances-efficiency-and-patient-safety-oracle-argus-platform-2025-07
23. IQVIA.ai, 16/03/2026 : https://iqvia.com/newsroom/2026/03/iqvia-unveils-iqvia-ai-a-unified-agentic-ai-platform ; QPPV européen externalisé, 14/07/2025 : https://www.iqvia.com/blogs/2025/07/why-more-pharma-companies-are-outsourcing-their-eu-qppv-function
24. IQVIA Vigilance Intake : https://www.iqvia.com/solutions/safety-regulatory-compliance/safety-and-pharmacovigilance/iqvia-vigilance-platform/iqvia-vigilance-intake ; Tech Mahindra et NVIDIA : https://biospectrumindia.com/news/16/25856/tech-mahindra-and-nvidia-collaborate-to-advance-drug-safety-using-agentic-ai.html
25. Cencora, rachat de PharmaLex, 03/01/2023 : https://investor.cencora.com/news/news-details/2023/AmerisourceBergen-Completes-Acquisition-of-PharmaLex/default.aspx
26. Biomapas, rachat de Delta PV, 04/08/2025 : https://www.biomapas.com/biomapas-acquires-delta-pv-to-expand-pharmacovigilance-capabilities/ ; rachat de Pinnaxis, 2026 : https://drug-dev.com/biomapas-acquires-pinnaxis-to-expand-drug-safety-technology-capabilities/
27. Qinecsa, rachat d'Insife, 21/03/2024 : https://qinecsa.com/news/stanley-capital-backed-portfolio-company-qinecsa-acquires-insife/
28. ProductLife Group, rachat de Stragen Services, 28/01/2025 : https://pharmafocus.com/articles/stragen-services-acquired-by-product-life-group
29. AB Cube, SafetyEasy : https://www.ab-cube.com/
30. Biologit : https://www.adaptcentre.ie/news-and-events/adapt-tcd-spin-out-biologit-raises-e1-million-from-investors/ ; https://tracxn.com/d/companies/biologit/__2vSaY40ASj0EFl3Q4AIADay-r0hhgovUW85PYHESr_0/funding-and-investors
31. Synapse Medicine, Medication Shield : https://www.synapse-medicine.com/pharmacovigilance
32. Prestataires français et européens : https://www.pharmya.com/en/about-us/ ; https://excelya.com/ ; https://atessiavigilances.com/responsable-de-pharmacovigilance-rpv-definition/ ; https://arriello.com/qppv/qppv-services/ ; https://insuvia.com/insights/qppv-outsourcing-in-eu-eea-and-its-benefits-for-mah/ ; https://www.ddregpharma.com/global-reach/pharmacovigilance-services-in-france
33. NextPV, coûts de la PV interne et externalisée : https://www.nextpvservices.com/services/
34. Anthropic, Claude for Healthcare and Life Sciences, 11/01/2026 : https://www.anthropic.com/news/healthcare-life-sciences
35. OpenAI et Orchestra Bio, 20/10/2026 : https://www.pharmtech.com/view/openai-bets-on-accelerating-drug-development-timelines-with-orchestra-bio ; OpenAI et Novo Nordisk, avril 2026 : https://www.fiercepharma.com/pharma/novo-taps-openai-deploy-ai-across-rd-manufacturing-and-corporate-functions
36. Salesforce, Life Sciences Cloud : https://www.salesforce.com/eu/solutions/industries/healthcare/life-sciences/
37. IntuitionLabs, *AI agents in pharmacovigilance* : https://intuitionlabs.ai/articles/ai-agents-pharmacovigilance
38. IntuitionLabs, *AI ROI in Pharmacovigilance*, 16/10/2026 : https://intuitionlabs.ai/articles/ai-roi-pharmacovigilance-business-case
39. Michael Page, grille de salaires « Responsable pharmacovigilance », édition 2027 : https://www.michaelpage.fr/grilles-de-salaires/life-sciences/affaires-pharmaceutiques-responsable-pharmacovigilance
40. France Travail, offres de postes de QPPV : https://candidat.francetravail.fr/offres/recherche/detail/4647911 ; https://candidat.francetravail.fr/offres/recherche/detail/191PYCC ; https://candidat.francetravail.fr/offres/recherche/detail/4461139
41. Règlement d'exécution (UE) 2025/1466, analyses : https://www.sidley.com/en/insights/newsupdates/2025/10/adapting-to-change-key-compliance-risks-under-the-revised-eu-pharmacovigilance-rules (octobre 2025) ; https://theentourage.us/en/insights/qppv-outsourcing-2025-1466-vertrag-audit (08/08/2026) ; https://ubc.com/insights/eu-post-marketing-compliance-what-regulation-2025-1466-means-for-your-pharmacovigilance-program/
42. EMA, *Medical literature monitoring* (périmètre de juin 2020) : https://www.ema.europa.eu/en/human-regulatory-overview/post-authorisation/pharmacovigilance-post-authorisation/medical-literature-monitoring
43. Swim Legal, obligations et responsabilités des laboratoires, 06/06/2026 : https://www.swim.legal/blog/pharmacovigilance-obligations-responsabilites-laboratoires
44. Anthropic, tarifs de l'API : https://platform.claude.com/docs/en/about-claude/pricing
45. Movianto, exploitation d'AMM : https://movianto.com/fr/services/services-a-valeur-ajoutee/exploitation-damm-centre-specialites-pharmaceutiques/
46. Commission européenne, *Regulatory framework on AI* : https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
47. Agence du numérique en santé, certification HDS : https://esante.gouv.fr/produits-services/hds
48. CIOMS, groupe de travail XIV, rapport du 04/12/2025 : https://cioms.ch/working-groups/working-group-xiv-artificial-intelligence-in-pharmacovigilance/
49. EMA, document de réflexion sur l'IA, 30/09/2024 : https://www.ema.europa.eu/en/use-artificial-intelligence-ai-medicinal-product-lifecycle-scientific-guideline
50. Parlement européen, Observatoire législatif, procédure 2023/0132(COD) : https://oeil.europarl.europa.eu/oeil/en/procedure-file?reference=2023/0132(COD)
51. Commission européenne, réforme de la législation pharmaceutique : https://health.ec.europa.eu/medicinal-products/legal-framework-governing-medicinal-products-human-use-eu/reform-eu-pharmaceutical-legislation_en
52. EMA, module I des GVP ; règlement 520/2012 : https://www.ema.europa.eu/documents/presentation/presentation-guideline-good-pharmacovigilance-practices-gvp-module-i-pharmacovigilance-systems-their_en.pdf ; https://www.legislation.gov.uk/eur/2012/520/chapter/II/section/2/data.htm
53. ANSM, déclaration de la personne de référence en pharmacovigilance (RPV) : https://ansm.sante.fr/vos-demarches/industriel/declarer-la-personne-de-reference-en-matiere-de-pharmacovigilance-en-france-rpv
54. MHRA Inspectorate, accords avec les prestataires de PV, 22/01/2018 : https://mhrainspectorate.blog.gov.uk/2018/01/22/mhra-gpvp-inspectorate-guide-to-marketing-authorisation-holder-considerations-for-agreements-with-pharmacovigilance-system-service-providers/
55. EMA, module VII des GVP (PSUR) ; BASG, FAQ : https://www.ema.europa.eu/en/documents/presentation/presentation-good-pharmacovigilance-practice-module-vii-periodic-safety-update-report_en.pdf ; https://basg.gv.at/en/companies/pharmacovigilance/faqs-pharmacovigilance
56. ALIGN, codage MedDRA par LLM (arXiv 2411.13163), 2024 : https://arxiv.org/pdf/2411.13163
57. Actes d'ALTA 2025, normalisation MedDRA : https://aclanthology.org/2025.alta-main.16
58. Revue systématique sur les LLM en pharmacovigilance, *Diagnostics*, 01/08/2026 : https://pmc.ncbi.nlm.nih.gov/articles/PMC13465311/
59. Epoch AI, *How Far Behind Are Open Models?*, 04/11/2024 : https://epoch.ai/blog/open-models-report
60. QbD Group, statistiques d'inspection GPvP de la MHRA 2022/2023 : https://info.qbdgroup.com/en/blog/mhra-good-pharmacovigilance-practice-inspection-metrics-and-findings
61. ANSM, FAQ des bonnes pratiques de PV sur le rôle du titulaire, juin 2018 : https://ansm.sante.fr/uploads/2021/01/28/faq-bppv-role-titulaire-juin2018.pdf
