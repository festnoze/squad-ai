# Observatoire des gains réels de rénovation : Moat et résistance aux LLM (red team)

Chapitre au 3 novembre 2026, en mode red team. Les références [S1] à [S19] renvoient aux sources en fin de chapitre (URL et date).

## Synthèse adverse

La thèse repose sur trois affirmations : personne ne relie travaux et consommation mesurée ; le délai de 12 à 24 mois protège le premier entrant ; un meilleur modèle accélère la base au lieu de la menacer. Les trois sont fragiles.

1. **"Personne ne relie" est faux au niveau statistique.** Le SDES et l'Insee apparient déjà des consommations mensuelles Linky et Gazpar issues d'un panel d'un million de logements avec les fichiers d'aides CEE, MaPrimeRénov' et CITE ; l'échantillon final porte sur environ 80 000 maisons et la version de septembre 2026 conclut que les gains réels représentent environ 42 % des gains conventionnels [S1] [vérifié]. La collecte se fait sans consentement, sur simple information des ménages, au titre de l'arrêté du 10 février 2023 [S2] [vérifié].
2. **Le délai incompressible protège les acteurs en place, pas l'entrant.** Hello Watt revendique 900 000 logements qui partagent quotidiennement leurs données Linky et Gazpar, dont plus de 100 000 ont déclaré des travaux, et publie depuis juillet 2026 des gains mesurés par geste [S3] [vérifié]. Ces historiques existent déjà ; un nouvel entrant part de zéro.
3. **L'État construit l'observatoire.** Pour la sixième période, la DGEC prévoit de collecter au registre les numéros de compteur (PDL, PCE) de chaque bénéficiaire, le coût des travaux et le montant des autres aides de chaque opération, et lance le programme PRODICEE (ADEME et huit copilotes dont CSTB, Cerema, CIRED, IPP) doté de 80 M€ maximum sur quatre ans pour l'évaluation et un système d'information anti-fraude [S4] [vérifié].
4. **La couche de contrôle documentaire est déjà une commodité tarifée.** Anti Fraude Française affiche 990 € HT par mois pour 200 dossiers puis 7,90 € par dossier supplémentaire [S8] [vérifié], soit 4,95 € par dossier inclus [estimé : 990 / 200]. La borne basse de la grille visée (5 à 20 €) est donc le prix public d'une plateforme complète existante.
5. **Le premier payeur ne porte pas le risque de sous-performance.** Les kWh cumac restent conventionnels : une pompe à chaleur conforme mais sous-performante ne fait pas annuler un certificat. L'obligé paie pour éviter l'annulation (non-conformité, fraude), pas pour connaître l'écart entre gain réel et gain conventionnel [hypothèse, déduite du caractère forfaitaire des fiches].

Ce qui tient : la détection de pannes grossières après un changement de chauffage, un rôle d'opérateur de mesure et vérification si quelqu'un paie à la performance, et l'appariement dossier par dossier dans le portefeuille d'un client privé.

## 1. Faisabilité technique aujourd'hui

### 1.1 Ce que les agents font déjà, brique par brique

| Brique | Fiabilité en 2026 | Ce qui échoue encore | Rôle réel du LLM |
|---|---|---|---|
| Extraction des devis et factures (montants, marques, références, surfaces, résistance thermique R, ETAS) | Élevée sur PDF natifs ; les meilleurs modèles obtiennent 82,8 à 85,9 sur 100 au score composite IDP (Nanonets OCR-3 85,9 ; GPT-5.4 83,5 ; Gemini-3-Pro 82,8) [S14] [vérifié] | Scans dégradés, tableaux multipages, factures retouchées ; 1 à 3 % d'erreurs de champ imposent une relecture ciblée [hypothèse] | Central mais commoditisé |
| Vérification RGE (France Rénov', Qualibat, Qualit'EnR) | Quasi déterministe à partir d'annuaires publics | Validité à la date exacte des travaux, domaine de qualification, sous-traitance, sociétés éphémères | Faible |
| Conformité aux fiches (BAR-TH-171, BAR-EN-101) | Bonne avec un moteur de règles assisté par LLM | Révisions fréquentes : les forfaits BAR-TH-171 et 172 sont actualisés pour la P6 [S4] [vérifié] | Moyen |
| Cohérence avec l'audit et le DPE | Moyenne | Appariement adresse et logement, DPE anciens ; coefficient de conversion de l'électricité passé de 2,3 à 1,9 en 2026 [S18] [vérifié] | Moyen |
| Prix de référence et détection d'anomalies | Dépend du volume | Démarrage à froid, biais du portefeuille des premiers clients | Nul (statistique) |
| Mesure du gain (Data Connect, ADICT, degrés-jours) | Méthodes publiques et ouvertes : CalTRACK et sa mise en oeuvre libre OpenEEmeter servent de base aux programmes payés à la performance en Californie, dans l'État de New York et en Oregon [S15] [vérifié] | Consentement, bruit individuel, changements d'occupation, panneaux solaires, véhicule électrique | Nul |
| Préparation des pièces pour le PNCEE et la contre-visite | Rédaction fiable | Décision, sanction et responsabilité restent humaines | Moyen |

### 1.2 Le verrou est statistique, pas linguistique

L'Insee mesure une baisse moyenne de 5,0 % de la consommation d'électricité des maisons chauffées à l'électricité après isolation, et de 6,6 % pour le gaz [S1] [vérifié] ; Hello Watt trouve -6 % d'électricité après isolation des combles [S3] [vérifié]. Si la consommation annuelle corrigée du climat d'un même ménage varie de 10 à 15 % d'une année sur l'autre [hypothèse], l'effet attendu d'une isolation est inférieur au bruit d'un seul logement.

Calcul de taille d'échantillon [estimé] : avec un écart type individuel de 12 %, un seuil de 5 % bilatéral et une puissance de 80 % (facteur 2,8), il faut n = (2,8 x 12 / 6)² ≈ 31 chantiers mesurés pour montrer qu'un installateur ne produit aucune économie sur un geste d'isolation, et n = (2,8 x 12 / 3)² ≈ 125 chantiers pour montrer qu'il n'en produit que la moitié de la moyenne. Pour l'isolation, le score par installateur n'a donc de sens qu'au-delà d'une centaine de chantiers mesurés par geste, soit deux à trois ans après le lancement.

À l'inverse, une pompe à chaleur air-eau qui remplace une chaudière gaz fait disparaître en moyenne 11 600 kWh de gaz par an et ajoute 4 400 kWh d'électricité [S3] [vérifié]. Une consommation de gaz résiduelle ou un appoint électrique permanent se voient sur un seul logement. **La promesse de mesure est crédible pour les changements de système de chauffage, pas pour l'isolation.**

Deux autres limites pèsent sur la promesse :

- **Le calendrier.** Le signal mesuré arrive au mieux 12 mois après les travaux. Les sociétés frauduleuses ont souvent disparu entre-temps [hypothèse]. La mesure est un outil de qualité, pas un outil anti-fraude ; la fraude se détecte sur les documents, les identités et les preuves photographiques, c'est-à-dire précisément sur la couche que les LLM banalisent. La pression anti-fraude est pourtant réelle (236 M€ de fraude aux CEE évitée en 2024 selon le Gouvernement [S7] [vérifié]) et les taux de contrôle déjà élevés (15 % sur site et 30 % par contact depuis le 1er janvier 2025 [S16] [hypothèse, source secondaire]) : c'est sur ce terrain documentaire que le budget des obligés se dépense.
- **Le consentement.** Data Connect impose un consentement d'une durée inférieure à trois ans, révocable à tout moment [S13] [vérifié]. L'historique antérieur aux travaux peut être récupéré au moment du consentement (profondeur à vérifier, de l'ordre de 24 à 36 mois selon les données) [hypothèse] : seule la période "après" est réellement incompressible, et elle l'est pour tout le monde.

### 1.3 Implication

La partie du produit qui exige des agents n'est pas défendable ; la partie défendable n'exige pas d'agents. Le LLM est ici un réducteur de coût du contrôle, pas la source de la valeur.

## 2. Scénarios de capacité

| Scénario | Ce que devient le produit | Valeur résiduelle | Qui capte la marge |
|---|---|---|---|
| (a) Modèles 2x meilleurs en 2027 | Contrôle documentaire quasi automatique. Les plateformes CEE en place (Anti Fraude Française, FastCRM, Consoneo) branchent les mêmes modèles. Coût d'inférence de l'ordre de 0,05 à 0,20 € par dossier [hypothèse] | Prix du contrôle tiré vers 2 à 5 € ; différenciation par la seule mesure | Éditeurs de plateformes CEE déjà installés et délégataires |
| (b) Modèles 10x avec computer use fiable, 2028-2029 | Un agent générique parcourt les annuaires RGE, l'espace client Enedis et le registre EMMY, relance les ménages par téléphone ou courriel | Contrôle à coût quasi nul. Restent les données mesurées appariées, le statut et la responsabilité | Fournisseurs de modèles, délégataires qui internalisent, organismes d'inspection accrédités (visite physique) |
| (c) Agents natifs dans Office, Workspace, Salesforce, SAP et l'outil métier | Copilot ou Gemini lisent les devis dans SharePoint ou Drive. Dans la filière, l'outil métier dominant est la plateforme CEE et le registre national refondu, qui intégrera le dépôt dès l'engagement [S4] [vérifié] | Le produit devient une fonctionnalité, sauf s'il possède la couche mesure | Éditeurs de suites et de plateformes CEE ; l'État pour le registre |
| (d) Modèles ouverts gratuits au niveau de la frontière | Inférence quasi gratuite et hébergeable en souverain | Abaisse la barrière pour l'administration (DGEC, PNCEE, PRODICEE), qui peut opérer en interne sans fournisseur étranger | L'État et les gros délégataires ; personne sur le contrôle |

Dans les quatre scénarios, la progression des modèles détruit le revenu du contrôle, premier revenu du plan. Elle épargne la couche mesure, mais celle-ci est menacée par des acteurs étrangers aux LLM : statistique publique, régulateur, application grand public.

## 3. Inventaire des actifs durables revendiqués

| Actif revendiqué | Réel ? | Temps de construction | Contournable, par qui |
|---|---|---|---|
| Base reliant prix, geste, installateur et gain mesuré | Partiellement. Les gains par geste sont déjà mesurés par le SDES (panel d'un million de logements) [S1] et par Hello Watt (900 000 logements) [S3]. Seul le lien installateur et ligne de devis est nouveau | 24 à 36 mois avant signification par installateur [estimé, section 1.2] | Oui : DGEC (PDL et coût des travaux au registre) [S4], PRODICEE, Hello Watt, grands délégataires sur leur propre portefeuille |
| Délai de 12 à 24 mois | Réel pour tous, entrant compris. Déjà consommé par ceux qui ont l'historique (données 2018-2024 au SDES) [S1] | Sans objet | Les détenteurs d'historique n'attendent pas |
| Consentements des ménages | Réels mais révocables, limités à moins de trois ans [S13], attachés à la relation du délégataire avec le ménage | 6 à 18 mois pour un volume utile [hypothèse] | L'État n'en a pas besoin [S2] [S4] ; le délégataire peut les recueillir dans son propre parcours |
| Contrats de tiers avec Enedis et GRDF | Faible. Data Connect et ADICT sont ouverts aux entreprises sur souscription | Quelques semaines à quelques mois [hypothèse] | Tout acteur |
| Intégrations (annuaires RGE, EMMY, plateformes CEE) | Faible | Quelques semaines | Éditeurs de plateformes CEE |
| Prix de référence mutualisés | Moyen à court terme, puis neutralisé : la refonte du registre collectera le coût des travaux et les autres aides de chaque opération [S4] [vérifié] | 12 à 24 mois | DGEC ; l'association Stop Fraudes (38 membres au lancement, 80 visés fin 2026) peut mutualiser elle-même [S11] [hypothèse, source secondaire] |
| Score de performance par installateur RGE | Potentiel réel mais lent (31 à 125 chantiers mesurés par geste) et juridiquement exposé (contestation, dénigrement, données des entrepreneurs individuels) | 3 ans et plus | Hello Watt (canal ménages), organismes de qualification |
| Agrément ou statut | Absent. L'accréditation d'organisme d'inspection existe mais interdit tout lien capitalistique avec les demandeurs et leurs mandataires [S17] [vérifié] | 12 à 18 mois [hypothèse] | Organismes d'inspection existants |
| Responsabilité portée | Absente de la thèse. Deviendrait un actif si l'offre garantissait les volumes contre l'annulation | Exige un bilan ou un assureur | Assureurs, délégataires |
| Effets de réseau | Faibles : les obligés sont concurrents et réticents à partager leurs prix | Lent | Le registre public les rend inutiles |
| Distribution, ancrage physique, relation humaine | Nuls au départ : délégataires et organismes d'inspection tiennent ménages, installateurs et contre-visites | Long | Délégataires et plateformes en place |

Le seul actif ni public ni reproductible en quelques mois est l'appariement opérationnel entre pièces, installateur et compteur dans le portefeuille d'un client qui le confie : un actif de service, pas une base exclusive.

## 4. Tests de résistance

| Test | Application à l'idée | Verdict |
|---|---|---|
| Un client obtient-il 80 % du résultat avec ChatGPT Enterprise et un stagiaire ? | Contrôle documentaire : oui, lecture, RGE et critères de fiche couvrent l'essentiel [hypothèse]. Mesure : un data scientist avec OpenEEmeter et Data Connect reproduit la méthode en quelques semaines ; l'obstacle réel (consentement, appariement PDL et dossier) est chez le délégataire, pas chez le fournisseur | Contrôle : mort. Mesure : survit faiblement |
| L'État peut-il le faire gratuitement ? | Oui, et c'est programmé : PDL et PCE au registre, coût des travaux, PRODICEE à 80 M€, panel SDES d'un million de logements [S1] [S4] | Test le plus dangereux |
| L'acteur installé peut-il l'ajouter en option en 12 mois ? | FastCRM revendique un contrôle par IA ramené de 25 minutes à moins de 2 minutes par dossier et un taux de rejet passé de 12-15 % à moins de 5 % [S9] [vérifié, déclaratif éditeur] ; Consoneo couvre plus de 170 fiches [S10] ; Certificall et Lysta couvrent preuve photographique et vérification des installateurs [S11] [S12] ; Effy plaide depuis 2023 pour un suivi de consommation après travaux [S19] | Oui |
| Le signal arrive-t-il à temps pour le payeur ? | Mesure à 12 mois au minimum ; les fraudeurs ont disparu ; le cumac reste forfaitaire | Non pour la fraude, oui pour la qualité |
| Le signal est-il détectable dossier par dossier ? | Isolation : non (5 à 7 % contre un bruit individuel supérieur) ; pompe à chaleur remplaçant une chaudière : oui | Restreindre au chauffage |
| Le payeur porte-t-il le risque mesuré ? | Non : l'obligé est exposé à l'annulation pour non-conformité, pas à l'écart entre réel et conventionnel | Problème de demande, pas de technologie |

## 5. Trois scénarios de mort et contre-mesures

### Mort n°1 : l'État ouvre l'observatoire (probabilité élevée, horizon 2027-2028)

La refonte du registre collecte PDL, PCE et coût des travaux dès l'engagement des opérations ; le SDES publie les gains réels par geste, région et type de logement ; PRODICEE livre un système d'information anti-fraude avec contrôles visuels et à distance [S4] [vérifié]. Le référentiel de l'entreprise devient un bien public gratuit, financé par le dispositif lui-même, dont l'enveloppe annuelle passe d'environ 6 Md€ en 2025 à plus de 8 Md€ en 2026 [S5] [vérifié], ordre de grandeur cohérent avec 1 050 TWhc par an valorisés à 8,60 €/MWhc, soit environ 9 Md€ au plafond [estimé] (volume [S5] multiplié par le prix EMMY de mai 2026 [S6]).

Contre-mesures crédibles : devenir prestataire ou coporteur de PRODICEE et des programmes CEE suivants ; construire sur la base publique au lieu de la dupliquer ; vendre ce que l'État n'opérera pas pour un acteur privé (préparation avant dépôt, relance des ménages, orchestration des contre-visites, dossier de défense en cas de contrôle).

### Mort n°2 : la commoditisation précède la maturation des données (probabilité élevée)

Le contrôle, vendu 5 à 20 € par dossier, tombe à 2 à 5 € dès que les plateformes en place intègrent les mêmes modèles (scénario a). La base mesurée exige 12 à 24 mois avant de produire de la valeur. Une équipe de quatre personnes coûte de l'ordre de 400 à 500 k€ par an [hypothèse] ; à 3 € de marge par dossier, l'équilibre demande 130 000 à 170 000 dossiers contrôlés par an [estimé : 400 à 500 k€ divisés par 3 €]. La trésorerie s'épuise avant que l'actif n'existe.

Contre-mesures : ne pas vendre le contrôle comme produit autonome mais l'inclure dans une offre de performance mesurée ; lever pour 24 mois de piste au minimum ; commencer par les pompes à chaleur, où le signal est lisible à 12 mois et où chaque opération pèse lourd en cumac.

### Mort n°3 : personne ne paie l'écart, et les règles changent en route (probabilité moyenne à élevée)

Les CEE restent conventionnels ; MaPrimeRénov' a été suspendue à l'été 2025, puis de nouveau au 1er janvier 2026, pour une durée indéterminée, faute de budget voté [S18] [vérifié], et les aides par geste pour l'isolation des combles et les fenêtres sont annoncées supprimées au 1er septembre 2026 [S3] [vérifié]. Si aucune bonification n'est liée à la performance mesurée, les obligés n'achètent pas d'abonnement de mesure, et le reporting taxonomie des banques continue de s'appuyer sur les classes de DPE plutôt que sur des kWh mesurés [hypothèse].

Contre-mesures : viser les payeurs qui portent le risque de performance (sociétés de tiers-financement régionales, opérateurs de contrats de performance énergétique, fabricants de pompes à chaleur soucieux de la qualité de leur réseau d'installateurs, assureurs) ; porter au COPIL CEE une proposition de bonification à la performance mesurée, sur le modèle des programmes payés à la performance adossés à CalTRACK aux États-Unis [S15].

## 6. Verdict adverse

### Note de résistance aux LLM : 4 sur 10

**Mécanisme.** La montée en puissance des modèles supprime la valeur de la couche de contrôle documentaire, qui porte le premier revenu du plan : dès le scénario (a), c'est une fonctionnalité des plateformes existantes, déjà vendue autour de 5 à 8 € le dossier [S8]. Elle ne crée pas de kWh mesurés : la couche mesure résiste aux LLM. Mais cette résistance ne devient pas un moat, pour trois raisons étrangères à l'IA : les données sont accessibles à l'État sans consentement [S2] et à Hello Watt avec consentement, à plus grande échelle [S3] ; la méthode est publique [S15] ; le premier payeur ne supporte pas le risque de sous-performance. La note n'est pas plus basse parce que l'appariement opérationnel, la gestion des consentements et un rôle reconnu de mesure et vérification ne sortent pas d'un modèle, et parce que la refonte du registre laisse une fenêtre de 18 à 24 mois [hypothèse].

### Version la plus résistante : vérificateur indépendant de performance des pompes à chaleur

Pivot recommandé :

- **Périmètre resserré** sur les opérations BAR-TH-171 et 172 (pompes à chaleur air-eau, eau-eau, sol-eau), où le signal se lit sur un seul logement et où chaque dossier pèse lourd ; l'isolation est abandonnée comme cible de mesure individuelle.
- **Produit** : vérification à 3 mois puis à 12 mois via Data Connect et ADICT (chaudière conservée, appoint électrique permanent, mauvais dimensionnement), déclenchement de la contre-visite, score qualité de l'installateur dans le réseau du client uniquement, sans publication.
- **Payeurs** : délégataires et obligés comme garantie qualité de portefeuille face aux contrôles renforcés de la P6, fabricants de pompes à chaleur, tiers-financeurs, et budgets de programmes CEE en coportage.
- **Positionnement** : aligner la méthode sur celle du SDES et de PRODICEE et la proposer comme protocole de référence, à la manière de CalTRACK aux États-Unis. L'entreprise devient l'opérateur du futur observatoire public, pas son concurrent.

Note de résistance de cette version : 6 sur 10. Le moat ne vient plus d'une base exclusive mais du statut de protocole de référence, de la responsabilité portée sur un signal fiable et de l'intégration au circuit de contrôle de la P6, trois actifs qu'un modèle 10 fois meilleur ne fournit pas.

## Sources

| Réf. | Source | Date |
|---|---|---|
| S1 | Insee et SDES, document de travail n°2025-16, "Effets de l'isolation thermique des logements sur la consommation réelle d'énergie résidentielle", version révisée : https://www.insee.fr/fr/statistiques/fichier/version-html/8607754/DT2025-16.pdf | Publié le 17 septembre 2026, consulté le 3 novembre 2026 |
| S2 | Arrêté du 10 février 2023 relatif à la collecte de données à des fins statistiques (article L. 142-1 du code de l'énergie) : https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000047254496 | Consulté le 3 novembre 2026 |
| S3 | Hello Watt, étude "Les travaux les plus efficaces" : https://cdn.hellowatt.fr/media/model_files/Etude_Hello_Watt_-_Les_travaux_les_plus_efficaces.pdf | Juillet 2026 |
| S4 | DGEC, COPIL CEE n°30, préparation de la 6e période : https://www.ecologie.gouv.fr/sites/default/files/documents/2025-07-02%20COPIL%20CEE%20n%C2%B030%20v8PostCopl_0.pdf | 2 juillet 2025 |
| S5 | Banque des Territoires, "Certificats d'économies d'énergie : le décret relatif à la sixième période est paru" (décret n°2025-1048 du 30 octobre 2025, 1 050 TWhc par an) : https://www.banquedesterritoires.fr/certificats-deconomies-denergie-le-decret-relatif-la-sixieme-periode-est-paru | Novembre 2025 |
| S6 | Opéra Énergie, prix des CEE d'après EMMY (8,60 €/MWhc en mai 2026) : https://opera-energie.com/barometres/prix-des-cee | Consulté le 3 novembre 2026 |
| S7 | Hellio, "Fraudes aux CEE : le point d'étape du Gouvernement" (236 M€ de fraude aux CEE évitée en 2024) : https://www.hellio.com/actualites/reglementation/fraude-cee | Mis à jour le 20 octobre 2025 |
| S8 | Anti Fraude Française, offre et tarifs : https://www.xn--anti-fraude-franaise-j1b.fr/ | Consulté le 3 novembre 2026 |
| S9 | Fidealis, "Mandataire CEE : piloter son réseau d'installateurs en 2026" (données FastCRM) : https://www.fidealis.com/innovations/mandataire-cee-piloter-reseau-installateurs/ | 25 juin 2026 |
| S10 | Consoneo, plateforme de conformité : https://consoneo.com/conformite | Consulté le 3 novembre 2026 |
| S11 | Certificall, "Fraude CEE : pourquoi les acteurs du dispositif passent enfin à l'offensive" : https://www.certificall.app/blog/fraude-cee-pourquoi-les-acteurs-du-dispositif-passent-enfin-a-loffensive/ | 17 mars 2026 |
| S12 | Lysta, vérification des installateurs et lutte contre la fraude aux CEE : https://www.lysta.fr/ | Consulté le 3 novembre 2026 |
| S13 | Enedis, guide des évolutions des API Data Connect 2026 : https://datahub-enedis.fr/wp-content/uploads/2026_Guide-des-evolutions-DataConnect.pdf | 2026, consulté le 3 novembre 2026 |
| S14 | IDP Leaderboard v1.5 : https://idp-leaderboard.org/ | Consulté le 3 novembre 2026 |
| S15 | LF Energy, OpenEEmeter : https://lfenergy.org/?p=6884 ; Recurve, programme payé à la performance de NYSERDA : https://recurve.com/blog/nyserda-and-dps-announce-plans-for-pay-for-performance-efficiency-in-new-york | Consultés le 3 novembre 2026 |
| S16 | Opéra Énergie, contrôle des CEE (taux de 15 % sur site et 30 % par contact depuis le 1er janvier 2025) : https://opera-energie.com/controle-cee/ | 7 avril 2026 |
| S17 | Seban Avocats, arrêté du 21 décembre 2025 sur la 6e période : https://www.seban-associes.avocat.fr/?p=127412 | 15 janvier 2026 |
| S18 | Hellio, "P6, MPR, DPE : les changements au 1er janvier 2026" : https://www.hellio.com/actualites/reglementation/p6-mpr-dpe-les-changements-au-1er-janvier-2026-hellio | Mis à jour le 5 mars 2026 |
| S19 | Effy, "Linky, nouvel allié de la transition énergétique du résidentiel ?" : https://www.effy.fr/flash-info/linky-nouvel-allie-de-la-transition-energetique-du-residentiel | 10 décembre 2024 |
