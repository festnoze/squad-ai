# Observatoire des gains réels de rénovation (C16) : étude de marché

Étude réalisée le 2026-11-03

Statut : rapport final. Verdict go conditionnel, valable uniquement pour la version pivot (vérification indépendante de la performance des pompes à chaleur). La version initiale de l'idée est déconseillée.

Conventions : [vérifié] source primaire ou deux sources concordantes ; [estimé] calcul à partir de données sourcées, méthode indiquée ; [hypothèse] ordre de grandeur sans source. Les renvois [n] pointent vers la liste numérotée de la section 13 (URL et date). Sauf mention contraire, les sources ont été consultées le 3 novembre 2026.

## 1. Résumé exécutif

**Verdict : go conditionnel, à condition de pivoter.** Telle qu'elle est formulée, l'idée résiste mal à la montée en puissance des modèles : 4 sur 10. Son premier revenu, le contrôle documentaire à 5 à 20 € par dossier, est déjà une commodité : Anti Fraude Française revient à environ 4,95 € le dossier [estimé : 990 € HT pour 200 dossiers][25]. Sa thèse de moat (« personne ne relie travaux et consommation mesurée ») est fausse au niveau statistique. L'Insee et le SDES apparient déjà sans consentement les relevés Linky et Gazpar d'un panel d'un million de logements avec les fichiers CEE et MaPrimeRénov' [vérifié][16][17], et Hello Watt suit 900 000 logements [vérifié, déclaratif][18]. Enfin, l'État construit lui-même l'observatoire : numéros de compteur et coût des travaux au registre, programme PRODICEE de 80 M€ [vérifié][5][6]. Le pivot recommandé, un **vérificateur indépendant de la performance des pompes à chaleur** (fiches BAR-TH-171 et 172), monte à 6 sur 10. Le signal y est lisible logement par logement, il touche le risque que l'obligé paie vraiment (la non-conformité, plafonnée par lot), et il s'aligne sur la méthode publique au lieu de la concurrencer.

| Indicateur | Valeur | Confiance |
|---|---|---|
| Flux CEE de la sixième période | 1 050 TWhc par an, plus de 8 Md€ par an [1][14] | [vérifié] |
| TAM France retenu (méthode ascendante) | environ 31 M€ par an ; réserve de valeur descendante d'environ 100 M€ | [estimé] |
| SAM France | environ 15 M€ (version initiale), 8 à 10 M€ (pivot) | [estimé] |
| TAM Europe retenu | environ 110 M€ par an (méthode ascendante) | [estimé], faible confiance hors France |
| SOM à 3 ans | environ 1,5 M€ d'ARR (fourchette 1,2 à 2 M€) | [estimé] |
| Comptes cœur | 50 à 70 (une trentaine de délégataires [2], 20 à 40 obligés outillés) | [estimé] |
| Panier annuel en deuxième année | environ 280 k€, marge brute de 55 à 75 % dans le pivot | [estimé] |
| Capital pour 24 mois | environ 1,5 M€ | [estimé] |

**Condition de succès numéro un** : prouver avant le mois 9, sur le portefeuille PAC d'un délégataire payant, que la mesure au compteur repère des non-conformités ensuite confirmées sur site (chaudière non déposée, appoint électrique permanent), avec un taux de consentement des ménages d'au moins 25 %. Sans cette preuve, ni les délégataires ni PRODICEE n'adopteront le protocole.

## 2. L'idée

### 2.1 Problème

La chaîne des certificats d'économies d'énergie (CEE) finance chaque année plus de 8 Md€ de travaux sur la base de gains conventionnels [vérifié][14]. Elle souffre de trois défauts.

- **Fraude et non-conformité.** Le PNCEE a rejeté plus de 28 TWhc en 2025 (environ 200 M€) et plus de 120 TWhc depuis 2016 [vérifié][1]. Le Gouvernement chiffre à 236 M€ la fraude aux CEE évitée en 2024 [vérifié, chiffre gouvernemental relayé][23].
- **Écart au réel.** La Cour des comptes juge les économies surestimées d'au moins 30 % [vérifié][15]. L'Insee mesure, pour l'isolation, des gains réels égaux à environ 42 % des gains conventionnels [vérifié][16].
- **Contrôle humain saturé.** Les demandeurs doivent faire contrôler 15 % des opérations sur site et 30 % par contact [vérifié][8]. 28 organismes d'inspection étaient suspendus ou retirés au 17 décembre 2025 [vérifié][3]. Le PNCEE a mandaté 4 500 contrôles sur site en 2025 [vérifié][1], soit environ 0,4 % des opérations résidentielles [estimé : 4 500 / 1,2 million].

### 2.2 Solution et rôle des agents

Deux agents, opérés pour des délégataires et des obligés, alimentent une base commune.

**Agent de contrôle, avant dépôt**
1. Il ingère les pièces (devis, facture, attestation sur l'honneur, photos, audit ou DPE) depuis le CRM CEE du client.
2. Il extrait les champs utiles : montants, marque, référence, ETAS, surface, résistance thermique.
3. Il vérifie la qualification RGE à la date des travaux et dans le bon domaine (annuaire France Rénov', Qualibat, Qualit'EnR).
4. Il contrôle la conformité à la version en vigueur de la fiche. BAR-TH-171 a connu trois versions en douze mois, la dernière (A82.5) au 1er septembre 2026 [vérifié][34].
5. Il confronte le dossier à l'audit et au DPE (base ADEME) et le prix aux références, classe les anomalies par gravité et projette le taux de non-conformité du lot.

**Agent de mesure, après travaux**
1. Il recueille le consentement du ménage, séparé de la prime, en se présentant comme une IA.
2. Il récupère l'historique et les relevés postérieurs par Enedis Data Connect et GRDF ADICT.
3. Il corrige les consommations du climat par les degrés-jours (méthode CalTRACK, mise en oeuvre libre OpenEEmeter [vérifié][37]).
4. Pour une PAC, il cherche à 3 mois puis à 12 mois une consommation de gaz résiduelle, un appoint électrique permanent ou un sous-dimensionnement.
5. Il déclenche la contre-visite et prépare les pièces pour l'organisme d'inspection et le PNCEE.

**Ce que gardent les humains** : contrôles sur site, relation avec les ménages et les installateurs, validation finale des alertes, décision de déposer, de financer ou de sanctionner, procédure contradictoire avec l'installateur signalé.

### 2.3 Produit en version 1 (forme recommandée)

Une application web et une API branchées sur le CRM CEE du client. Elle comprend un tableau de bord par lot (anomalies triées, projection du taux de non-conformité face aux seuils de 14, 12 et 10 %), un module de suivi PAC (alertes à 3 et 12 mois), un dossier de défense exportable en cas de contrôle, et un score qualité des installateurs visible du seul client, jamais publié. L'isolation reste couverte par le contrôle documentaire, pas par la mesure individuelle (voir 9.1).

## 3. Pourquoi maintenant

| Échéance | Effet | Source |
|---|---|---|
| 30 juin 2025 : loi contre les fraudes aux aides publiques | Sanction avant délivrance, publication des noms, contrôle visuel à distance par un tiers (cadre à écrire) | [1][8] [vérifié] |
| 1er janvier 2026 : sixième période (2026-2030) | 1 050 TWhc par an, +27 % par rapport à 2025 ; au moins 278 obligés carburants attendus en 2026, contre 189 en 2025 | [1][10][57] [vérifié] |
| 1er avril 2026 | Indépendance capitalistique entre organisme d'inspection, demandeur et mandataire | [3] [vérifié] |
| Mai 2026, 2027, 2028 | Contrôle sur site des PAC air/eau à 50 %, 75 % puis 100 % | [11] [vérifié] |
| 27 juillet 2026 : arrêté sur les contrôles | Un lot au-delà de 14 % de non-conformités en 2026 (12 % en 2027, 10 % en 2028) n'est déposable que pour ses opérations contrôlées satisfaisantes | [12] [vérifié] |
| 2026-2027 : refonte du registre EMMY | Dépôt dès l'engagement, coût des travaux, numéros de compteur PDL et PCE | [5][1] [vérifié] |
| 2025-2029 : PRODICEE | 80 M€ HT au plus : panels Linky et Gazpar, système d'information anti-fraude, contrôle à distance | [6][7] [vérifié] |
| 2028 | Interdiction de louer les logements classés F (G depuis 2025) | [61] [vérifié] |

Deux arbitrages de calendrier. Sur les PAC, l'arrêté du 15 décembre 2025 prévoyait 50 % de contrôle sur site en 2027 et 100 % en 2028 [4] ; le calendrier publié en avril 2026 avance le palier de 50 % à mai 2026 [11]. Nous retenons le plus récent ; les deux convergent sur 100 % en 2028, la seule date décisive pour l'idée. Ensuite, les travaux engagés en 2026 donnent des gains mesurés en 2027-2028, au moment où se prépare la septième période (vers 2029) [hypothèse]. Arriver en 2028, c'est subir les méthodes de PRODICEE au lieu de les co-écrire. Côté coût, la lecture automatisée d'un dossier revient à 0,8 à 1,2 € revue humaine comprise [hypothèse, voir 7.3], ce qui rend le contrôle exhaustif du portefeuille économiquement possible.

## 4. Marché

### 4.1 France

**Valeur sous-jacente.** Le Gouvernement annonce plus de 8 Md€ par an [vérifié][14]. Selon le prix retenu (prix implicite des rejets du PNCEE, environ 7,1 €/MWhc, ou prix spot de 8,60 €/MWhc en classique [13] et environ 15 €/MWhc en précarité [1]), la fourchette va de 7,5 à 10,8 Md€ [estimé]. Les chapitres divergeaient sur ce point ; nous retenons 9 Md€.

**Méthode descendante (réserve de valeur).** Le coût actuel du contrôle et de la conformité atteint environ 64 M€ par an [estimé : 1,2 million de dossiers x 34 € d'instruction, plus contrôles par contact et visites sur site]. S'y ajoutent 12 M€ de pertes évitables captables (10 % des rejets résidentiels), 20 M€ d'évaluation (dont PRODICEE, environ 16 M€ par an [7]) et 5 M€ côté banques. Total : **environ 100 M€ par an**, fourchette 70 à 130 M€ [estimé]. Le volume de 1,2 million d'opérations résidentielles par an vient de 4,5 Md€ de CEE résidentiels (50 % de 9 Md€ [hypothèse]) divisés par 3 000 à 4 000 € par opération [hypothèse] [estimé].

**Méthode ascendante (TAM retenu).**

| Segment | Calcul | Total |
|---|---|---|
| Contrôle des dossiers CEE | 1,2 million x 10 € | 12,0 M€ |
| Abonnements et rapports | 60 comptes x 45 k€ [hypothèse] | 2,7 M€ |
| Mesure | 216 000 logements actifs x 25 € (30 % mesurables, 30 % de consentement [hypothèse]) | 5,4 M€ |
| Contrôle MaPrimeRénov' | 307 731 dossiers en 2025 [50] x 8 € | 2,4 M€ |
| Banques | 126 030 éco-PTZ [49] x 15 €, plus reporting | 2,4 M€ |
| Accompagnateurs Rénov', collectivités, organismes d'inspection | Paniers de 1,5 à 25 k€ [hypothèse] | 6,4 M€ |
| **Total** | | **environ 31 M€** [estimé] |

L'écart entre 100 et 31 M€ est le résultat le plus instructif : au tarif envisagé, le produit capte un tiers de ce que le processus coûte. Une tarification à la valeur (30 à 50 € par dossier) ne se défend que si la réglementation reconnaît la preuve à distance ou les économies mesurées, ce que recommande la Cour des comptes [vérifié][15] et qu'étudie PRODICEE [vérifié][6]. Le chapitre concurrence évalue la dépense adressable à 5 à 20 M€ : ce chiffre ne couvre que le contrôle CEE (12 M€ ici). Nous retenons 31 M€ comme TAM, segments hors CEE inclus.

**SAM France : environ 15 M€** [estimé] pour la version initiale. On part des segments contrôle, abonnements et mesure (20,1 M€). On retire 40 % des volumes, internalisés par les plus grands acteurs [hypothèse], puis on ajoute la moitié des segments accompagnateurs et collectivités. **Dans le pivot, 8 à 10 M€** [estimé]. Le calcul retient 150 000 à 250 000 opérations PAC par an [hypothèse, à vérifier sur le registre EMMY] vérifiées à 30 €, soit 4,5 à 7,5 M€. S'y ajoutent le contrôle documentaire du reste des portefeuilles à 2 à 4 € et 2 à 3 M€ de fabricants, tiers-financeurs et programmes [hypothèse]. Si la mesure devient une modalité reconnue de contrôle à distance, le prix défendable rejoint 50 à 80 € par PAC, soit environ 20 % d'une visite à 150 à 400 € [32]. La brique PAC vaudrait alors 10 à 20 M€ [estimé].

**SOM à 3 ans : environ 1,5 M€ d'ARR** (fourchette 1,2 à 2 M€) [estimé]. Le chapitre marché obtenait 1,5 à 2 M€ avec 120 000 dossiers à 10 €. Or le contrôle de l'isolation se vend 3 à 5 € [25][26], ce qui retire environ 0,7 M€. Le pivot compense par la vérification PAC : 4 délégataires ou obligés à environ 250 k€, plus 2 à 3 contrats fabricants ou programmes à 100 à 150 k€ [hypothèse]. L'objectif suppose de signer au moins un délégataire de premier rang.

### 4.2 Nombre de clients cibles

| Segment | Nombre | Confiance |
|---|---|---|
| Délégataires P6 | près d'une trentaine de demandes au 19 décembre 2025 [2] | [vérifié] |
| Grands obligés produisant leurs CEE | 20 à 30, sur plusieurs centaines d'obligés [57] | [estimé] |
| Structures Mon Accompagnateur Rénov' | 1 492 structures, 3 987 accompagnateurs (juin 2026) [53] | [vérifié] |
| Banques distributrices d'éco-PTZ | 126 030 prêts en 2025 pour environ 2 Md€, plus de 80 % par les réseaux mutualistes [49] | [vérifié] |
| Organismes d'inspection | environ 70 accrédités, dont 28 suspendus ou retirés, soit 40 à 45 actifs | [estimé : 28 rapporté aux « près de 40 % » du rapport au Parlement [8][3]] |
| Entreprises RGE (sujets du score, pas payeurs) | 63 000 sur 560 000 entreprises du bâtiment [56] | [vérifié] |

Les chapitres divergeaient sur les accompagnateurs (1 336 structures début 2025, 1 492 en juin 2026) : nous retenons le chiffre le plus récent. L'hypothèse de 20 à 40 organismes d'inspection du chapitre marché correspond aux organismes encore actifs. La consolidation est voulue par l'État : le décret P6 relève les volumes minimaux de délégation [vérifié][57], ce qui réduira encore le nombre de comptes.

### 4.3 Europe et monde

| Zone | TAM descendant | TAM ascendant | SOM à 3 ans |
|---|---|---|---|
| France | environ 100 M€ | environ 31 M€ | environ 1,5 M€ |
| Europe (UE et Royaume-Uni) | environ 400 M€ [hypothèse : budgets d'obligations environ 4 fois ceux de la France] | **environ 110 M€** [estimé : 3,5 fois le TAM France, accès inégal aux compteurs] | France plus un pilote espagnol |
| Monde | environ 1 Md€ [hypothèse] | environ 300 M€ [hypothèse : programmes des fournisseurs américains de 8 à 9 Md$ par an, dont 3 à 5 % d'évaluation et de vérification] | non pertinent |

L'Espagne est la tête de pont naturelle : certificats CAE depuis le 26 janvier 2023, vérification confiée à des organismes accrédités par l'ENAC [vérifié][58]. Le Royaume-Uni ouvre une fenêtre avec la fin de l'ECO4 au 31 décembre 2026 et des défauts de qualité d'installation reconnus en janvier 2025 [vérifié][59]. L'Allemagne est peu adaptée faute de compteurs communicants [hypothèse]. Aux États-Unis, la place est tenue par Recurve et Bidgely [38][39]. Hors de France, rien de significatif n'est atteignable à 3 ans.

### 4.4 Croissance, moteurs et freins

Moteurs : une obligation P6 environ 49 % au-dessus de la moyenne annuelle de la cinquième période [estimé : 1 050 contre environ 705 TWhc][1] ; un prix des CEE précarité passé d'environ 8 à plus de 15 €/MWhc entre début 2022 et fin 2025 [vérifié][1], qui double presque le coût d'un dossier frauduleux ; des seuils qui se durcissent jusqu'en 2028 ; la transposition de la directive 2024/1275, qui vise une baisse de 16 % de l'énergie primaire résidentielle en 2030 [vérifié][60]. Freins : la volatilité de MaPrimeRénov', suspendue à l'été 2025 puis au 1er janvier 2026 et rouverte le 23 février 2026 [vérifié][24][52], avec des demandes de rénovation d'ampleur divisées par quatre [vérifié][51] ; la substitution publique (PRODICEE, registre) ; la consolidation des délégataires. Les CEE, financés par les factures d'énergie, restent moins exposés que MaPrimeRénov' au budget de l'État.

## 5. Clients et segments

### 5.1 Client idéal

Un délégataire P6 ou un obligé intermédiaire (distributeur de carburant, fournisseur alternatif) qui traite 10 000 à 100 000 opérations résidentielles par an, avec une forte part de PAC air/eau et un back-office de 5 à 30 ETP sans équipe data [hypothèse pour les tailles]. Il a un déclencheur actif : plan d'action ou suspension d'instruction par le PNCEE, lot proche du seuil, renouvellement de délégation sans reconduction automatique [vérifié][2].

### 5.2 Personas et douleur quantifiée

| Persona | Douleur | Ce qui le convainc |
|---|---|---|
| Directeur CEE ou conformité (décideur) | 1 000 isolations de combles de 80 m² en zone H2 représentent 112 GWhc, soit 0,96 M€ bloqués si le lot dépasse le seuil [estimé : 1 400 kWhc/m² [33] x 80 m² x 1 000 x 8,60 €/MWhc [13]]. Pénalité pour CEE manquant : 15 €/MWhc en classique, 20 €/MWhc en précarité [vérifié][9]. Depuis 2015 : 6,3 TWhc annulés et 30 M€ de sanctions [vérifié][8] | Baisse mesurée du taux de non-conformité sur un lot réel |
| Responsable du back-office (utilisateur) | Pour 30 000 dossiers : environ 6 ETP de contrôle documentaire [hypothèse : 20 minutes par dossier] et 0,7 à 1,8 M€ de visites sur site [estimé : 15 % x 30 000 x 150 à 400 € [32]] | Anomalies triées, pièces prêtes pour la contre-visite |
| DPO et RSSI (bloqueur) | Consentement Linky et Gazpar, analyse d'impact, avis d'imposition | Analyse d'impact rédigée, hébergement en UE |
| Directions commerciale et juridique (bloqueur) | Crainte qu'une mesure fragilise l'actif : gains réels d'environ 42 % des gains conventionnels [vérifié][16] | Résultats confidentiels, publication agrégée et consentie |

Payeurs secondaires du pivot, qui portent eux le risque de performance : fabricants de PAC soucieux de leur réseau d'installateurs, sociétés de tiers-financement régionales, opérateurs de contrats de performance énergétique, assureurs (l'Agence Qualité Construction copilote PRODICEE [vérifié][6]) [hypothèse sur leur disposition à payer]. Persona bancaire : la direction de la finance durable, dont les encours verts reposent sur des DPE conventionnels.

### 5.3 Processus d'achat

| Segment | Cycle [hypothèse] | Exigences |
|---|---|---|
| Délégataire | 3 à 6 mois | Pilote payant sur l'historique, contrat de sous-traitance RGPD, intégration au CRM et au dépôt EMMY |
| Obligé intermédiaire | 6 à 12 mois | Référencement, questionnaire sécurité, réversibilité |
| Grand obligé | 12 à 18 mois | Appel d'offres, ISO 27001, clauses d'audit |
| Banque | 12 à 24 mois | DORA (applicable depuis le 17 janvier 2025), secret bancaire |
| Collectivité, opérateur | 3 à 12 mois | Commande publique, hébergement souverain |

Le budget est le coût de revient du MWhc chez le délégataire, l'OPEX de conformité chez l'obligé : l'achat se vend comme un transfert de dépense depuis le contrôle délocalisé et les visites mal ciblées.

Deux bloqueurs sont propres à l'idée. D'abord, l'obligé peut **ne pas vouloir savoir** : le cumac est forfaitaire et l'écart au réel ne lui coûte rien tant que le dossier est conforme. Dans le pivot, la mesure ne sert pas à chiffrer l'écart mais à détecter une non-conformité, par exemple une chaudière conservée alors que l'opération suppose son remplacement [hypothèse, à confirmer sur la fiche A82.5]. L'argument se retourne alors en faveur de la mesure. Ensuite, le consentement ne peut pas conditionner la prime (article 7, paragraphe 4, du RGPD), d'où un taux incertain.

## 6. Concurrence

### 6.1 Acteurs en place

| Acteur | Ce qu'il tient | Menace pour C16 |
|---|---|---|
| État : DGEC, PNCEE, registre EMMY, ADEME, SDES | Vérifications automatisées sur 100 % des dossiers [1] ; registre avec PDL, PCE et coût des travaux [5] ; PRODICEE (ADEME et 8 copilotes dont CSTB, Cerema, AQC, IPP) [6] ; panel SDES d'un million de logements [16] | La plus forte : légitime et gratuit. N'offre pas de service avant dépôt aux demandeurs [hypothèse] |
| Effy | 100 000 foyers par an, plus de 5 000 artisans [vérifié, déclaratif][21] ; plaide depuis 2023 pour un suivi de consommation après travaux [20] | Juge et partie, mais prêt à capter la mesure si elle devient obligatoire |
| Hellio | 175 M€ de chiffre d'affaires 2024, 100 000 logements rénovés [vérifié, déclaratif][22] | Peut internaliser |
| Une vingtaine d'autres délégataires (Sonergia, ACE...) | Flux de dossiers, contrôle interne | Clients plutôt que concurrents |
| Organismes d'inspection (Bureau Veritas, PME) | Monopole du contrôle sur site opposable | Partenaires des contre-visites, payés à la visite |
| Plateformes CEE : FastCRM, Anti Fraude Française, Consoneo, Certificall, Lysta | Contrôle IA à 50 € HT par utilisateur et par mois [vérifié][26] ; 990 € HT par mois pour 200 dossiers [vérifié][25] ; plus de 170 fiches couvertes [28] ; preuve photographique et vérification des installateurs [29][30] | Ont déjà banalisé le contrôle documentaire |

FastCRM revendique un contrôle ramené de 25 minutes à moins de 2 minutes par dossier et un taux de rejet passé de 12 à 15 % à moins de 5 % [vérifié, déclaratif éditeur][27]. L'association Stop Fraudes (38 membres au lancement, 80 visés fin 2026) peut mutualiser elle-même des signaux [hypothèse, source secondaire][29].

### 6.2 Startups

| Startup | Financement | Recouvrement avec C16 |
|---|---|---|
| Hello Watt (France) | 12 M€ en série A, novembre 2023 [vérifié][19] | **Fort.** 900 000 logements connectés, dont plus de 100 000 avec travaux déclarés ; gains par geste publiés en juillet 2026 ; retenu avec ENGIE sur un appel à projets PAC en septembre 2026 [vérifié][18]. Principal concurrent du pivot |
| Argile (France) | Non communiqué | Moyen : logiciel IA pour artisans RGE (devis, dossiers d'aides), 49 à 119 € par utilisateur et par mois [vérifié][31] |
| Kocliko (France) | 3,5 M$ cumulés [estimé][42] | Moyen : mesure en chauffage collectif, 50 000 logements [vérifié, déclaratif][41] |
| Deepki et Metry | Rachat de Metry le 6 août 2026 [estimé][42] | Faible aujourd'hui, mais capacité européenne d'agrégation de compteurs |
| Recurve (États-Unis) | 38,27 M$ cumulés [estimé][42] | Analogue le plus proche de l'agent de mesure, absent d'Europe [38] |
| Bidgely (États-Unis) | 98,95 M$ cumulés [estimé][42] | Désagrégation des courbes, repère un appoint électrique, vend aux fournisseurs [39] |
| Build Test Solutions (Royaume-Uni) | Non communiqué | Déperdition mesurée par compteur communicant [40] |

Aucune levée française identifiée ne porte sur le contrôle tiers des dossiers CEE. La mesure au compteur est un métier financé aux États-Unis (plus de 130 M$ cumulés pour Recurve et Bidgely [estimé][42]).

### 6.3 Grands acteurs du numérique

| Acteur | Annonce | Probabilité de couverture native d'ici 2028 [hypothèse] |
|---|---|---|
| Microsoft | Agents autonomes Copilot Studio, 21 octobre 2024 [45] | 30 à 40 % pour un agent interne de contrôle documentaire chez un grand obligé |
| Salesforce | Agentforce, 29 octobre 2024 ; Energy & Utilities Cloud, Engie cliente [44] | 25 % via intégrateurs |
| OpenAI, Anthropic, Google | ChatGPT agent, juillet 2025 [48] ; Claude for Financial Services, 15 juillet 2025 [47] ; Gemini Enterprise, 10 octobre 2025 [46] | 10 % chacun |
| SAP, ServiceNow | Agents génériques | Moins de 10 % |
| État | Collecte PDL et PCE, système anti-fraude PRODICEE | 60 à 70 % pour une mesure statistique agrégée des gains par geste |

Les laboratoires d'IA ne viseront pas un marché de 5 à 20 M€ adossé à un dispositif national ; ils accélèrent le « faire soi-même » des grands obligés.

### 6.4 Substituts et positionnement

Substituts : IA généraliste en interne (20 à 60 € par utilisateur et par mois [hypothèse]), externalisation vers les organismes d'inspection, statu quo (coût caché des rejets), attente de l'État. Sur la carte qui croise la position (tiers neutre ou partie prenante) et l'objet vérifié (conformité au dépôt ou performance mesurée), le seul quadrant libre en France est **tiers neutre et performance mesurée**. Il est libre parce qu'il est petit, réglementé, physique, local et lent, et parce que celui qui détient les dossiers est juge et partie. L'État y entre par la porte statistique.

### 6.5 Intensité concurrentielle

Le chapitre concurrence notait 5 sur 10 sans intégrer Anti Fraude Française, Consoneo, Certificall, Lysta ni le panel SDES, relevés par la red team. Nous retenons **6 sur 10 pour l'idée initiale** : 8 sur 10 sur le contrôle documentaire, 4 sur 10 sur les prix de référence (que le registre rendra publics [5]), 4 sur 10 sur la mesure. **Le pivot ramène l'intensité à 4 à 5 sur 10**, avec Hello Watt et ENGIE comme rival principal.

## 7. Modèle économique et prix

### 7.1 Points de référence

| Référence | Prix | Confiance |
|---|---|---|
| Contrôle sur site, opération simple | 150 à 400 € | [estimé, source secondaire unique][32] |
| Contrôle sur site, opération complexe | 800 à 1 800 € | [estimé, source secondaire unique][32] |
| CRM CEE avec contrôle IA | 50 € HT par utilisateur et par mois | [vérifié][26] |
| Plateforme anti-fraude | environ 4,95 € par dossier inclus, 7,90 € au-delà | [vérifié][25] |
| Cours des CEE | 8,60 €/MWhc (mai 2026) | [vérifié][13] |
| Valeur CEE d'une isolation de combles | 960 à 1 460 € | [estimé][33][13] |
| Valeur CEE d'une PAC sous Coup de pouce | 2 500 à 5 000 € | [hypothèse] |

À 5 € par dossier, le contrôle représente 0,3 à 0,5 % de la valeur CEE d'une isolation de combles ; à 20 €, 1,4 à 2 % [estimé]. La fourchette haute de la thèse initiale ne se justifie que pour les PAC et les rénovations d'ampleur.

### 7.2 Modèle retenu (pivot)

| Module | Modèle | Prix [hypothèse] |
|---|---|---|
| Vérification PAC : contrôle avant dépôt, mesure à 3 et 12 mois, déclenchement de contre-visite | Par opération | 25 à 40 € |
| Contrôle documentaire du reste du portefeuille | À l'usage, minimum annuel de 30 k€ | 2 à 4 € par dossier, en ticket d'entrée |
| Observatoire réseau : score qualité des installateurs du client, référentiel de prix réservé aux contributeurs | Abonnement | 30 à 80 k€ par an |
| Fabricants, tiers-financeurs, programmes coportés | Forfait projet | 100 à 200 k€ |

Le partage d'économies est exclu, car les économies reviennent aux ménages. Une commission sur les sommes recouvrées auprès d'installateurs fautifs reste accessoire, pour préserver la neutralité face au PNCEE et aux organismes d'inspection.

### 7.3 Unit economics

Cas d'un délégataire médian en deuxième année : 30 000 dossiers, dont 5 000 PAC [hypothèse].

| Poste | Montant annuel |
|---|---|
| Vérification PAC : 5 000 x 32 € | 160 k€ |
| Contrôle documentaire : 25 000 x 3 € | 75 k€ |
| Observatoire réseau | 45 k€ |
| **Panier annuel** (100 à 150 k€ en première année) | **280 k€** [estimé] |
| Coût de service du contrôle : 0,8 à 1,2 € par dossier (inférence 0,10 à 0,40 € ; revue humaine de 15 % des dossiers à 6 minutes et 45 €/h, environ 0,70 € ; infrastructure 0,05 à 0,10 €) | 24 à 36 k€ [hypothèse] |
| Coût de service de la mesure : 8 à 15 € par PAC (consentement, relances, rapports) | 40 à 75 k€ [hypothèse] |
| Customer success et veille réglementaire (0,1 à 0,15 ETP) | 10 à 15 k€ [hypothèse] |
| **Marge brute** | **55 à 75 %** [estimé] |
| CAC (vente menée par les fondateurs, cycle de 6 à 9 mois) | 40 à 70 k€ [hypothèse] |
| Récupération du CAC | 6 à 12 mois [estimé] |

La marge est plus basse que dans la grille initiale (68 à 81 % selon le chapitre clients), parce que la mesure coûte plus cher à servir que la lecture. Rétention attendue : 85 à 90 % des clients, rétention nette de 115 à 125 % [hypothèse], adossées à des obligations qui courent jusqu'en 2030. Plafond du segment cœur : 50 à 70 comptes à 150 à 300 k€, soit 8 à 20 M€ d'ARR en France [estimé]. Une équipe de 5 personnes (650 à 700 k€ par an [hypothèse]) atteint l'équilibre vers 4 comptes matures [estimé : 680 k€ / (280 k€ x 65 %)].

### 7.4 Coût d'inférence

La lecture multimodale de 10 à 30 pages coûte 0,10 à 0,40 € par dossier aux tarifs publics des API en 2026 [hypothèse], soit moins de 5 % du panier. Avec des modèles deux fois meilleurs, elle tombe à 0,05 à 0,20 € [hypothèse]. Un meilleur modèle réduit surtout la revue humaine (environ 0,70 € par dossier), et ce gain profite autant aux concurrents qu'à C16.

## 8. Go-to-market

### 8.1 Canaux

- **Vente menée par les fondateurs** jusqu'à 10 clients.
- **ATEE, Club C2E et son groupe de travail Contrôle**, où la filière écrit ses règles de contrôle.
- **Éditeurs de CRM CEE**, en intégration et revente : l'Observatoire leur fournit la mesure par API au lieu de les combattre sur le contrôle.
- **Organismes d'inspection**, pour les contre-visites ciblées, par contrat seulement et sans lien capitalistique [3].
- **PRODICEE et appels à programmes CEE**, pour la légitimité et le financement.
- **Fabricants de PAC**, pour atteindre les réseaux d'installateurs.

Hello Watt est à traiter d'emblée, soit comme partenaire de données sur des logements déjà connectés, soit comme concurrent frontal.

### 8.2 Les 10 premiers clients (mois 0 à 18)

1. **Mois 0 à 3** : contrats de tiers Data Connect et ADICT, analyse d'impact RGPD, protocole de mesure PAC aligné sur CalTRACK et sur la méthode du SDES, cartographie des 30 délégataires et 20 obligés par déclencheur (plan d'action PNCEE, part de PAC, lots bloqués).
2. **Mois 2 à 6** : trois rétro-audits payants (15 à 25 k€ chacun [hypothèse]) sur 3 000 à 10 000 dossiers déjà déposés, avec une mesure rétrospective consentie sur des PAC posées depuis plus de 12 mois. L'historique exposé par les API (24 à 36 mois [hypothèse, à vérifier contractuellement]) permet une première preuve sans attendre 12 à 24 mois.
3. **Mois 6 à 9** : premier contrat annuel chez un délégataire ou un obligé intermédiaire qui veut assainir son portefeuille.
4. **Mois 9 à 18** : dix clients, dont 6 délégataires ou obligés, 1 fabricant de PAC, 1 tiers-financeur ou programme régional, 1 organisme d'inspection partenaire payant et 1 pilote bancaire sur un portefeuille d'éco-PTZ.

### 8.3 Les 100 premiers (mois 18 à 48)

| Segment | Clients | Panier |
|---|---|---|
| Délégataires et obligés (proche de la saturation) | 30 à 40 | 150 à 300 k€ |
| Caisses régionales mutualistes | 15 à 25 | 50 à 150 k€ |
| Opérateurs d'accompagnement et collectivités | 20 à 30 | 10 à 30 k€ |
| Fabricants, tiers-financeurs, assureurs | 5 à 10 | 100 à 200 k€ |
| Europe (Espagne d'abord, via des partenaires) | 5 à 10 | 50 à 150 k€ |

Paniers et volumes : [hypothèse]. Ce passage demande 3 à 4 commerciaux grands comptes et 2 responsables du succès client [hypothèse]. Le cœur CEE seul ne suffit pas à atteindre 100 clients.

### 8.4 Preuves à apporter

- Une étude de cas chiffrée : précision des alertes confirmée sur site, client ramené sous le seuil de 14 % puis de 12 %.
- Une note méthodologique cosignée par un laboratoire, cohérente avec l'approche de l'Insee et du SDES [16].
- Le taux de consentement mesuré en pilote.
- Une feuille de route ISO 27001, une analyse d'impact partageable et une classification AI Act documentée.

## 9. Moat et résistance à la montée en puissance des LLM

### 9.1 Le verrou est statistique, pas linguistique

Après isolation, l'Insee mesure une baisse moyenne de 5,0 % de la consommation d'électricité et de 6,6 % de celle de gaz [vérifié][16] ; Hello Watt trouve -6 % d'électricité après isolation des combles [vérifié][18]. Supposons une variation annuelle individuelle de 12 % [hypothèse]. Il faut alors environ 31 chantiers mesurés pour montrer qu'un installateur ne produit aucune économie, et 125 pour montrer qu'il n'en produit que la moitié [estimé : n = (2,8 x 12 / 6)² et (2,8 x 12 / 3)²]. Un score d'installateur en isolation n'a donc de sens qu'après deux à trois ans. À l'inverse, une PAC air-eau qui remplace une chaudière gaz retire en moyenne 11 600 kWh de gaz par an et ajoute 4 400 kWh d'électricité [vérifié][18]. Un gaz résiduel ou un appoint permanent se voient sur un seul logement, dès les premiers mois de chauffe. **La mesure est crédible pour les changements de système de chauffage, pas pour l'isolation.**

### 9.2 Actifs durables

| Actif revendiqué | Réalité | Contournable par |
|---|---|---|
| Base prix, geste, installateur, gain mesuré | Partielle : les gains par geste sont déjà mesurés par le SDES et Hello Watt ; seul le lien entre ligne de devis et installateur est nouveau | DGEC (registre), PRODICEE, Hello Watt, grands délégataires |
| Délai de 12 à 24 mois | Réel pour tous, entrant compris ; déjà consommé par ceux qui ont l'historique (données 2018-2024 au SDES) [16] | Détenteurs d'historique |
| Consentements des ménages | Révocables, limités à moins de trois ans [vérifié][35] | Délégataires dans leur propre parcours ; l'État n'en a pas besoin [17] |
| Contrats Enedis et GRDF | Ouverts à toute entreprise, en quelques semaines à quelques mois [hypothèse] | Tout acteur |
| Prix de référence mutualisés | Neutralisés quand le registre collectera le coût des travaux [5] | DGEC, association Stop Fraudes |
| Statut de protocole de référence (pivot) | Absent aujourd'hui ; atteignable par alignement sur le SDES et PRODICEE | Organismes d'inspection, ADEME |

Le seul actif ni public ni reproductible en quelques mois est l'appariement opérationnel entre pièces, installateur et compteur dans le portefeuille confié par un client. C'est un actif de service, pas une base exclusive. La partie du produit qui exige des agents n'est pas défendable ; la partie défendable n'exige pas d'agents.

### 9.3 Scénarios de capacité

L'extraction documentaire est déjà mûre : les meilleurs modèles obtiennent 82,8 à 85,9 sur 100 au score composite de l'IDP Leaderboard [vérifié][43].

| Scénario | Effet | Ce qui reste |
|---|---|---|
| Modèles 2x meilleurs (2027) | Les plateformes CEE en place branchent les mêmes modèles ; prix du contrôle tiré vers 2 à 5 € [hypothèse] | La mesure seule différencie |
| Modèles 10x avec computer use fiable (2028-2029) | Un agent générique parcourt les annuaires RGE, l'espace client Enedis et le registre, et relance les ménages | Données mesurées appariées, statut, responsabilité portée |
| Agents natifs (Copilot, Gemini, Agentforce, plateformes CEE, registre refondu) | Le contrôle devient une fonctionnalité de l'outil métier | La couche mesure, si elle est possédée |
| Modèles ouverts au niveau de la frontière | Inférence quasi gratuite et souveraine : l'administration peut opérer seule | Le service opérationnel aux demandeurs |

Dans les quatre scénarios, la progression des modèles détruit le premier revenu du plan initial et épargne la mesure. Mais la mesure est menacée par des acteurs étrangers aux LLM : la statistique publique, le régulateur et une application grand public.

### 9.4 Tests de résistance

| Test | Verdict |
|---|---|
| ChatGPT Enterprise et un stagiaire font-ils 80 % du travail ? | Contrôle : oui. Mesure : un data scientist avec OpenEEmeter reproduit la méthode en quelques semaines, mais pas l'appariement entre compteur et dossier |
| L'État peut-il le faire gratuitement ? | Oui, c'est programmé : test le plus dangereux |
| Un acteur installé peut-il l'ajouter en 12 mois ? | Oui pour le contrôle (FastCRM, Consoneo) |
| Le signal arrive-t-il à temps ? | Non pour la fraude à l'isolation (12 mois, sociétés disparues) ; oui pour la PAC (3 mois en saison de chauffe) |
| Le signal est-il lisible dossier par dossier ? | Isolation : non. PAC remplaçant une chaudière : oui |
| Le payeur porte-t-il le risque mesuré ? | Non pour l'écart au conventionnel ; oui quand la mesure révèle une non-conformité |

### 9.5 Ce qui tuerait l'idée, et contre-mesures

1. **L'État ouvre l'observatoire** (probabilité élevée, 2027-2028). Le registre collecte PDL et coût des travaux, le SDES publie les gains par geste, PRODICEE livre son système anti-fraude. Contre-mesure : devenir prestataire ou coporteur de PRODICEE, construire sur la base publique, et vendre ce que l'État n'opère pas pour un acteur privé (préparation avant dépôt, relance des ménages, orchestration des contre-visites, dossier de défense).
2. **La commoditisation précède la maturation des données** (probabilité élevée). À 3 € de marge par dossier, une équipe de 4 personnes (400 à 500 k€ par an [hypothèse]) doit contrôler 130 000 à 170 000 dossiers par an pour s'équilibrer [estimé]. Contre-mesure : ne jamais vendre le contrôle seul, lever 24 mois de piste, commencer par les PAC.
3. **Personne ne paie l'écart et les règles changent en route** (probabilité moyenne à élevée). Les CEE restent conventionnels ; MaPrimeRénov' a été suspendue deux fois en six mois [24] ; les aides par geste pour les combles et les fenêtres ont été annoncées supprimées au 1er septembre 2026 [vérifié][18]. Contre-mesure : viser les payeurs qui portent le risque de performance, et porter au COPIL CEE une bonification à la performance mesurée, sur le modèle des programmes payés à la performance adossés à CalTRACK [37].

### 9.6 Version la plus résistante

**Vérificateur indépendant de la performance des pompes à chaleur.** Le périmètre se limite aux opérations BAR-TH-171 et 172. Le produit vérifie à 3 puis 12 mois la chaudière conservée, l'appoint permanent et le dimensionnement, déclenche la contre-visite et tient un score qualité visible du seul client. La méthode, alignée sur celle du SDES et de PRODICEE, est proposée comme protocole de référence, à la manière de CalTRACK aux États-Unis. L'entreprise devient l'opérateur du futur observatoire public, pas son concurrent.

Note de résistance : **6 sur 10**. Le moat ne vient plus d'une base exclusive mais de trois actifs qu'un modèle 10 fois meilleur ne fournit pas : le statut de protocole, la responsabilité portée sur un signal fiable et l'intégration au circuit de contrôle de la P6. Son talon d'Achille : Hello Watt et ENGIE travaillent sur le même terrain [18].

## 10. Réglementation et risques

### 10.1 AI Act

L'usage cœur (contrôle de conformité et détection de fraude sur des dossiers d'obligés privés, sous décision humaine) ne figure pas à l'annexe III. Il se documente au titre de l'article 6, paragraphes 3 et 4 (tâche préparatoire sous revue humaine). Il bascule en **haut risque** dans deux cas : une autorité publique l'utilise pour accorder ou récupérer une aide (Anah, annexe III, point 5 a), ou une banque utilise les scores pour évaluer la solvabilité d'un ménage ou d'un entrepreneur individuel (point 5 b). Les contrats doivent exclure ces usages. Côté dates, l'Omnibus numérique reporte les obligations de l'annexe III au 2 décembre 2027. La transparence de l'article 50 s'applique depuis le 2 août 2026 : l'agent qui sollicite les ménages doit se présenter comme une IA. La maîtrise de l'IA (article 4) s'impose depuis février 2025 [vérifié, deux sources concordantes][54].

### 10.2 RGPD et données de comptage

La société est sous-traitante pour le contrôle documentaire, responsable de traitement pour le référentiel mutualisé. La transmission des données Linky et Gazpar à un tiers exige un consentement révocable, d'une durée inférieure à trois ans [vérifié][35]. Dès le 1er janvier 2027, Enedis dissocie les accès et ne transmet que les données nécessaires [vérifié][36]. Il faut donc demander les index quotidiens, et la courbe de charge seulement pour diagnostiquer une PAC. Le consentement ne peut pas conditionner la prime. Une analyse d'impact est quasi certaine (grande échelle, croisement de sources, avis d'imposition).

### 10.3 Sectoriel, concurrence, hébergement, responsabilité

- **Sectoriel.** L'arrêté du 28 septembre 2021 sur les contrôles a été modifié le 27 juillet 2026 [12]. La loi du 30 juin 2025 publie les sanctions et crée le contrôle visuel à distance par un tiers, dont le cadre reste à écrire [8]. Pour rester neutre, la société ne sera ni mandataire ni organisme d'inspection, puisque l'accréditation interdit tout lien capitalistique avec les demandeurs [vérifié][55]. L'échantillon réglementaire reste dû.
- **Concurrence.** Mutualiser prix et primes entre obligés concurrents relève des lignes directrices horizontales européennes de 2023 sur l'échange d'informations. Il faut des données agrégées, historiques et anonymisées, sous une gouvernance écrite.
- **Hébergement.** Hébergement en UE, fournisseur de modèles en région UE sans réutilisation pour l'entraînement. L'HDS ne s'applique pas ; SecNumCloud seulement si l'État ou l'Anah l'exigent ; DORA et secret bancaire pour les banques.
- **Responsabilité.** L'obligé reste responsable devant le PNCEE. Il faut un plafond contractuel à 12 mois de facturation et une assurance RC professionnelle [hypothèse]. Un score d'installateur diffusé expose au dénigrement : d'où une procédure contradictoire et l'absence de publication.

### 10.4 Matrice des risques

| Risque | Probabilité | Impact | Réponse |
|---|---|---|---|
| L'État restitue gratuitement des références de gains par geste | Élevée | Élevé | Se positionner en prestataire et en opérateur du protocole |
| Commoditisation du contrôle documentaire | Quasi certaine | Moyen dans le pivot, élevé dans la version initiale | Contrôle en ticket d'entrée, valeur dans la mesure PAC |
| Taux de consentement inférieur à 20 % | Moyenne | Élevé | Consentement intégré au parcours du délégataire ; seuil d'arrêt en pilote |
| Hello Watt et ENGIE prennent la vérification PAC | Moyenne | Élevé | Neutralité vis-à-vis des obligés concurrents d'ENGIE, ou partenariat de données |
| Volatilité des dispositifs (MaPrimeRénov', fiches révisées trois fois par an) | Élevée | Moyen | Dépendre des CEE plutôt que de MaPrimeRénov' ; veille réglementaire facturée |
| Cycles de vente plus longs que la trésorerie | Moyenne | Élevé | Rétro-audits payants dès le mois 3, 24 mois de piste |
| Droit de la concurrence sur la mutualisation | Moyenne | Moyen | Données agrégées et différées, gouvernance écrite |
| Bascule en haut risque AI Act | Faible | Moyen | Exclusion contractuelle des usages Anah et crédit |
| Action en dénigrement par un installateur | Moyenne | Faible à moyen | Score non publié, procédure contradictoire |

## 11. Feuille de route 18 mois

**Équipe.** Quatre personnes au démarrage, six au mois 18 [hypothèse] : un dirigeant commercial issu de la filière CEE (délégataire ou obligé) ; un responsable data, mesure et vérification (CalTRACK, séries temporelles énergétiques) ; un ingénieur agents et intégrations ; un expert réglementaire CEE et conformité. Viennent ensuite un responsable du succès client et un second ingénieur.

**Capital.** Environ 1,5 M€ pour 24 mois de piste [estimé : 5 à 6 ETP à environ 100 k€ chargés, plus juridique (analyse d'impact, AI Act, assurance), sécurité (feuille de route ISO 27001) et infrastructure, soit 650 à 750 k€ par an]. Des compléments non dilutifs restent possibles : appels à programmes CEE, Bpifrance, ADEME [hypothèse].

| Période | Jalons | Critère d'arrêt ou de poursuite |
|---|---|---|
| Mois 0 à 3 | Contrats Data Connect et ADICT ; analyse d'impact ; protocole PAC ; 2 lettres d'intention | Aucune lettre d'intention : arrêt |
| Mois 3 à 6 | 3 rétro-audits payants ; mesure rétrospective sur PAC ; taux de consentement mesuré ; premier contact avec PRODICEE | Consentement inférieur à 20 % ou précision des alertes inférieure à 50 % : arrêt ou repli |
| Mois 6 à 9 | Premier contrat annuel ; note méthodologique cosignée ; premières alertes à 3 mois | Aucun contrat annuel : arrêt |
| Mois 9 à 12 | 4 clients, 5 000 PAC suivies, environ 400 k€ d'ARR | Moins de 2 clients : réduire l'équipe |
| Mois 12 à 18 | 8 à 10 clients dont 1 fabricant et 1 programme ; 0,6 à 0,8 M€ d'ARR ; candidature comme prestataire de PRODICEE ; exploration en Espagne | Levée d'amorçage ou trajectoire vers l'équilibre (environ 4 comptes matures) |

Cibles d'ARR et de clients : [hypothèse].

**Métriques suivies** : dossiers contrôlés et PAC suivies ; taux de consentement ; part des PAC avec gaz résiduel ou appoint permanent ; précision des alertes confirmées sur site ; taux de non-conformité des lots clients face aux seuils ; délai entre la pose et le premier signal ; ARR, rétention nette, CAC et délai de récupération.

## 12. Scorecard et verdict

| Critère (sur 10) | Idée initiale | Pivot PAC | Justification |
|---|---|---|---|
| Attractivité du marché | 5 | 4 | Flux de plus de 8 Md€ et urgence datée, mais TAM adressable de 31 M€, 50 à 70 comptes et plafond de 8 à 20 M€ d'ARR ; le pivot réduit encore le périmètre |
| Résistance aux LLM | 4 | 6 | Contrôle banalisé ; la mesure PAC résiste et peut devenir un protocole |
| Espace concurrentiel | 4 | 5 | État, plateformes CEE et Hello Watt ; le quadrant neutre et mesuré reste libre |
| Faisabilité | 6 | 6 | API et méthodes ouvertes, inférence peu coûteuse ; consentement et cycles de vente incertains |
| Risque réglementaire inversé | 4 | 5 | Fiches et aides volatiles, RGPD lourd, droit de la concurrence ; le pivot s'appuie sur la loi de 2025 |
| **Globale** | **4,5** | **5,5** | Moyenne arrondie |

**Verdict : go conditionnel**, pour la version pivot uniquement ; la version initiale est un no-go. Conditions :

1. Signer un délégataire ou un obligé intermédiaire sur un rétro-audit PAC payant avant le mois 6, et sur un contrat annuel avant le mois 9.
2. Mesurer un taux de consentement d'au moins 25 % et une précision des alertes d'au moins 50 %, confirmée sur site.
3. Obtenir avant fin 2027 une place dans le dispositif public : prestataire de PRODICEE, protocole discuté au COPIL CEE, ou reconnaissance dans le cadre du contrôle à distance.
4. Régler la relation avec Hello Watt (partenariat, ou différenciation par la neutralité) avant la levée d'amorçage.
5. Ne jamais vendre le contrôle documentaire comme produit autonome.

Le projet vise une entreprise rentable de 5 à 20 M€ d'ARR, pas une trajectoire classique de capital-risque, sauf si la mesure devient une modalité réglementaire du contrôle.

## 13. Sources

Toutes consultées le 3 novembre 2026 ; la date indiquée est celle de publication quand elle est connue.

1. DGEC, webinaire « 6e période des CEE », 2 décembre 2025 : https://www.ecologie.gouv.fr/sites/default/files/documents/2025-12-02%20Webinaire%20DGEC%20P6%20CEE%20vweb.pdf
2. DGEC, Flash info délégations P6, 19 décembre 2025 : https://www.ecologie.gouv.fr/sites/default/files/documents/2025-12-19%20Flash%20Info%20delegations%20P6.pdf
3. DGEC, lettre d'information CEE, décembre 2025 : https://www.ecologie.gouv.fr/sites/default/files/documents/2025-12%20lettre%20d%27infos%20CEE%20vf.pdf
4. DGEC, Flash info sur l'arrêté du 15 décembre 2025 (BAR-TH-171 et 172), 19 décembre 2025 : https://www.ecologie.gouv.fr/sites/default/files/documents/2025-12-19%20-%20Flash%20Info%20Publication%2078%C3%A8me%20arr%C3%AAt%C3%A9%20et%20recensement%20des%20engagements%20BAR-TH-171%20et%20172_0.pdf
5. DGEC, COPIL CEE n° 30, 2 juillet 2025 : https://www.ecologie.gouv.fr/sites/default/files/documents/2025-07-02%20COPIL%20CEE%20n%C2%B030%20v8PostCopl_0.pdf
6. Convention PRODICEE, 4 juin 2026 : https://www.ecologie.gouv.fr/sites/default/files/documents/PRODICEE_convention_signee_20260604.pdf
7. ADEME, appel à financeurs PRODICEE, 6 août 2025 : https://www.ecologie.gouv.fr/sites/default/files/documents/2025-08-06_M_Flash_Info_Appel_%C3%A0_Financeurs-PRODICEE.pdf
8. Gouvernement, rapport au Parlement sur le dispositif CEE, 2025 : https://www.ecologie.gouv.fr/sites/default/files/documents/Rapport%20au%20Parlement%20-%20Dispositif%20CEE.pdf
9. DGEC, lettre d'information CEE, juillet 2026 : https://www.ecologie.gouv.fr/sites/default/files/documents/2026-07%20lettre%20d%27infos%20CEE%20vf.pdf
10. Banque des Territoires, décret P6, 4 novembre 2025 : https://www.banquedesterritoires.fr/certificats-deconomies-denergie-le-decret-relatif-la-sixieme-periode-est-paru
11. Banque des Territoires, contrôles renforcés des PAC, 29 avril 2026 : https://www.banquedesterritoires.fr/certificats-deconomies-denergie-vers-des-controles-renforces-pour-les-pompes-chaleur
12. Selectra, arrêté du 27 juillet 2026, 29 juillet 2026 : https://selectra.info/energie/actualites/renovation-energetique/controles-cee-non-conformite-fraude-arrete-juillet-2026 ; texte : https://www.actu-environnement.com/ae/reglementation/arrete-du-27-07-2026-ecor2620284a-40064.php
13. Opéra Énergie, prix des CEE (indice Emmy), mai 2026 : https://opera-energie.com/outils-et-donnees-marche/prix-des-cee/
14. prix-carburant.eu, enveloppe CEE de plus de 8 Md€, 28 octobre 2025 : https://prix-carburant.eu/article/enveloppe-cee-plus-de-8-milliards-euros-2026
15. Banque des Territoires, Cour des comptes sur les CEE, 17 septembre 2024 : https://www.banquedesterritoires.fr/certificats-deconomies-denergie-la-cour-des-comptes-plaide-pour-une-reforme-structurelle-dampleur
16. Insee et SDES, document de travail 2025-16, version révisée du 17 septembre 2026 : https://www.insee.fr/fr/statistiques/fichier/version-html/8607754/DT2025-16.pdf ; https://www.statistiques.developpement-durable.gouv.fr/effets-de-lisolation-thermique-des-logements-sur-la-consommation-reelle-denergie-residentielle
17. Arrêté du 10 février 2023 relatif à la collecte de données à des fins statistiques : https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000047254496
18. Hello Watt, étude « Les travaux les plus efficaces », 2 juillet 2026 : https://cdn.hellowatt.fr/media/model_files/Etude_Hello_Watt_-_Les_travaux_les_plus_efficaces.pdf ; espace presse : https://www.hellowatt.fr/presse/
19. Maddyness, « Hello Watt lève 12 millions d'euros », 6 novembre 2023 : https://www.maddyness.com/2023/11/06/hello-watt-leve-12-millions-deuros-pour-accelerer-la-fin-des-passoires-thermiques/
20. Effy, « Linky, nouvel allié de la transition énergétique du résidentiel ? », 10 décembre 2024 : https://www.effy.fr/flash-info/linky-nouvel-allie-de-la-transition-energetique-du-residentiel
21. Effy, « Qui sommes-nous » : https://www.effy.fr/qui-sommes-nous
22. Hellio, site institutionnel et analyse P6 mise à jour le 21 septembre 2026 : https://www.hellio.com/ ; https://www.hellio.com/actualites/reglementation/sixieme-periode-cee
23. Hellio, « Fraudes aux CEE : le point d'étape du Gouvernement », 20 octobre 2025 : https://www.hellio.com/actualites/reglementation/fraude-cee
24. Hellio, « P6, MPR, DPE : les changements au 1er janvier 2026 », 5 mars 2026 : https://www.hellio.com/actualites/reglementation/p6-mpr-dpe-les-changements-au-1er-janvier-2026-hellio
25. Anti Fraude Française, offre et tarifs : https://www.xn--anti-fraude-franaise-j1b.fr/
26. FastCRM, offre délégataires et mandataires : https://www.fastcrm.ai/mandataires
27. Fidealis, « Mandataire CEE : piloter son réseau d'installateurs en 2026 », 25 juin 2026 : https://www.fidealis.com/innovations/mandataire-cee-piloter-reseau-installateurs/
28. Consoneo, plateforme de conformité : https://consoneo.com/conformite
29. Certificall, « Fraude CEE : pourquoi les acteurs du dispositif passent enfin à l'offensive », 17 mars 2026 : https://www.certificall.app/blog/fraude-cee-pourquoi-les-acteurs-du-dispositif-passent-enfin-a-loffensive/
30. Lysta, vérification des installateurs : https://www.lysta.fr/
31. Argile, tarifs et article P6 : https://www.argile.ai/tarifications ; https://www.argile.ai/blog/cee-et-p6-ce-que-tout-artisan-rge-doit-savoir-pour-rester-conforme
32. Controlecee.com, tarifs des organismes de contrôle, 5 janvier 2026 : https://www.controlecee.com/organismes-de-controle-cee/
33. Opéra Énergie, fiche BAR-EN-101, 1er juin 2026 : https://opera-energie.com/bar-en-101/
34. Fiche BAR-TH-171, version A82.5 au 1er septembre 2026 : https://atee.fr/system/files/2026-06/BAR-TH-171%20vA82-5%20%C3%A0%20compter%20du%2001-09-2026_1.pdf
35. Enedis, guide des évolutions des API Data Connect, 2026 : https://datahub-enedis.fr/wp-content/uploads/2026_Guide-des-evolutions-DataConnect.pdf
36. Selectra, données Linky et RGPD en 2027, 25 juin 2026 : https://selectra.info/energie/actualites/marche/donnees-linky-rgpd-enedis-2027
37. LF Energy, OpenEEmeter : https://lfenergy.org/projects/openeemeter/ ; Recurve, programme payé à la performance de NYSERDA : https://recurve.com/blog/nyserda-and-dps-announce-plans-for-pay-for-performance-efficiency-in-new-york
38. Recurve, site institutionnel : https://www.recurve.com/
39. Bidgely, site institutionnel : https://www.bidgely.com/
40. Build Test Solutions, site institutionnel : https://www.buildtestsolutions.com/
41. Kocliko, site institutionnel : https://www.kocliko.co/
42. CB Insights, profils financiers (Deepki, Metry, Recurve, Bidgely, Kocliko, Hello Watt) : https://www.cbinsights.com/company/deepki/financials ; https://www.cbinsights.com/company/metry/financials ; https://www.cbinsights.com/company/recurve/financials ; https://www.cbinsights.com/company/bidgely/financials ; https://www.cbinsights.com/company/kocliko/financials ; https://www.cbinsights.com/company/hello-watt/financials
43. IDP Leaderboard v1.5 : https://idp-leaderboard.org/
44. Salesforce, Energy & Utilities Cloud et disponibilité d'Agentforce, 29 octobre 2024 : https://www.salesforce.com/energy-utilities/ ; https://www.salesforce.com/news/press-releases/2024/10/29/agentforce-general-availability-announcement/
45. Microsoft, agents autonomes dans Copilot Studio, 21 octobre 2024 : https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/unlocking-autonomous-agent-capabilities-with-microsoft-copilot-studio/
46. Google Cloud, « Introducing Gemini Enterprise », 10 octobre 2025 : https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise
47. Anthropic, « Claude for Financial Services », 15 juillet 2025 : https://www.anthropic.com/news/claude-for-financial-services
48. OpenAI, « Introducing ChatGPT agent », juillet 2025 : https://openai.com/index/introducing-chatgpt-agent/
49. Les-energies-renouvelables.eu, bilan SGFGAS de l'éco-PTZ 2025, 23 juillet 2026 : https://www.les-energies-renouvelables.eu/article/actualites/reglementations/126-030-proprietaires-ont-decroche-un-eco-pret-a-taux-zero-en-2025-un-record-porte-par-trois-banques-seulement-1378/
50. Effy, bilan 2025 de MaPrimeRénov', 24 février 2026 : https://www.effy.fr/pro/actualite/maprimerenov-dresse-son-bilan-2025
51. Connaissance des Énergies (AFP), demandes MaPrimeRénov' divisées par quatre, 27 juillet 2026 : https://www.connaissancedesenergies.org/afp/maprimerenov-les-nouvelles-demandes-divisees-par-quatre-apres-la-baisse-des-aides-260727
52. Gouvernement, réouverture de MaPrimeRénov', février 2026 : https://www.info.gouv.fr/actualite/reouverture-de-maprimerenov
53. Assemblée nationale, question écrite n° 15426, réponse du 9 juin 2026 : https://questions.assemblee-nationale.fr/q17/17-15426QE.htm
54. Quantic Avocats, Omnibus numérique et AI Act, 22 juillet 2026 : https://www.quantic-avocats.com/2026/07/22/ai-act-digital-omnibus-report-obligations-haut-risque/ ; Genee, août 2026 : https://www.genee.tech/blog/eu-ai-act-digital-omnibus-obligations-haut-risque-decembre-2027
55. Seban Avocats, arrêté du 21 décembre 2025 sur la sixième période, 15 janvier 2026 : https://www.seban-associes.avocat.fr/?p=127412
56. FFB, entreprises RGE, 13 novembre 2025 : https://www.nouvelle-aquitaine.developpement-durable.gouv.fr/IMG/pdf/2025_moment_pro_rge_ffb.pdf
57. Synthèse de la consultation publique sur le décret P6, 2025 : https://www.consultations-publiques.developpement-durable.gouv.fr/IMG/pdf/synthese_de_la_consultation_publique_decret_p6_vf.pdf
58. MITECO, système des certificats d'économies d'énergie (CAE) : https://www.miteco.gob.es/es/energia/eficiencia/cae.html
59. Ofgem, Energy Company Obligation (ECO4) : https://www.ofgem.gov.uk/environmental-and-social-schemes/energy-company-obligation-eco
60. Commission européenne, directives efficacité énergétique et performance énergétique des bâtiments : https://energy.ec.europa.eu/topics/energy-efficiency/energy-efficiency-targets-directive-and-rules/energy-efficiency-directive_en ; https://energy.ec.europa.eu/topics/energy-efficiency/energy-performance-buildings/energy-performance-buildings-directive_en
61. Loi n° 2021-1104 Climat et résilience : https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000043956924
