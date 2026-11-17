# PRRC externe et registre PMCF mutualisé pour PME medtech : Moat et résistance aux LLM (red team)

## Synthèse adverse

La thèse repose sur trois piliers : la PRRC déclarée dans EUDAMED, un corpus non public de questions d'organismes notifiés (ON) et un registre PMCF multi-fabricants. La direction est juste : quand le coût de rédaction tend vers zéro, la valeur migre vers la signature et la donnée clinique auditable. Mais l'entreprise décrite capte mal cette valeur. La PRRC externe est un service banalisé, vendu à partir de 4 000 euros par an. Le corpus restera longtemps trop petit face aux cabinets installés. Dans les catégories citées (rachis, paroi abdominale), des sociétés savantes tiennent déjà des registres. Enfin, un registre lancé en 2027 produira ses données à 24 mois après les deux échéances de transition.

**Note de résistance aux LLM : 4/10 pour l'idée telle que formulée, 6/10 pour la version pivotée proposée en section 6.**

## 1. Faisabilité technique aujourd'hui (novembre 2026)

### 1.1 Ce que les agents font déjà de façon fiable

- **Premiers jets documentaires** (annexes II et III, checklist des exigences générales de sécurité et de performance (GSPR), plans PMS et PMCF, PSUR) : les modèles actuels produisent un brouillon structuré et exploitable à partir de gabarits MDCG. Le coût marginal d'un brouillon est déjà quasi nul. Ce n'est plus un différenciateur.
- **Tri bibliographique** : dans une évaluation publiée en janvier 2025, GPT-4 atteignait une exactitude de 0,92 au tri sur résumés, 0,75 au tri sur texte intégral et 0,81 en extraction de données ; Claude-3 obtenait respectivement 0,69, 0,69 et 0,59 [vérifié] (Chen et Zhang, arXiv 2502.15702, https://arxiv.org/abs/2502.15702, consulté le 2026-11-03). Ces modèles sont depuis largement dépassés : la question n'est plus la faisabilité mais le coût de vérification humaine.
- **Veille et surveillance** (MAUDE, ANSM, EUDAMED, littérature) : tâche de collecte et de classement déjà industrialisée. L'autrichien Flinn a levé 20 M$ en série A le 19 février 2026 pour automatiser la PMS, l'évaluation de la littérature et la veille réglementaire des medtech [vérifié] (https://tech.eu/2026/02/19/flinn-secures-20m-to-develop-ai-tools-for-product-lifecycle-management-in-medtech-and-pharma/, consulté le 2026-11-03).
- **Traçabilité Jira, Git et eQMS** : Ketryx (série B de 39 M$ le 4 septembre 2025) commercialise des « agents IA validés » depuis mai 2025. Depuis le 31 mars 2026, un serveur MCP en bêta rend ChatGPT, Claude et Copilot « conscients de la conformité » [vérifié] (https://www.ketryx.com/news, consulté le 2026-11-03). La couche d'intégration promise par l'idée est donc déjà un produit d'éditeur.

### 1.2 Ce qui échoue encore

- **Erreur résiduelle d'extraction clinique** : même à 95 % d'exactitude par champ, un rapport d'évaluation clinique (CER) de 500 champs contient environ 25 erreurs [estimé : 5 % x 500]. La relecture ligne à ligne reste obligatoire, et c'est elle qui coûte.
- **Équivalence (MDCG 2020-5)** : pour les classes III et les implantables, elle exige un accès contractuel aux données du dispositif équivalent. Le blocage est juridique, pas rédactionnel.
- **Accès aux dossiers patients informatisés** : éditeurs hétérogènes, peu d'API, réticence des responsables sécurité. Le computer use dans un SI hospitalier reste un pari [hypothèse].
- **Actions irréversibles** : rapport d'incident (MIR), enregistrement UDI et EUDAMED, déclaration de conformité. Une erreur y devient une non-conformité juridique, d'où une validation humaine systématique.

### 1.3 Conséquence pour la promesse

| Brique | Faisable par agent en 2026 | Ce qui reste rare | Résistance aux LLM |
|---|---|---|---|
| Rédaction doc technique, PSUR, plans | Oui (brouillon) | Relecture experte | Nulle |
| Revue bibliographique reproductible | Oui avec contrôle humain | Protocole et jugement | Faible |
| Veille MAUDE, ANSM, EUDAMED | Oui | Aucun | Nulle |
| Traçabilité Jira, Git, eQMS | Oui, déjà vendue | Aucun | Nulle |
| Signature PRRC | Non (personne physique) | Qualification, assurance | Forte mais banale |
| Données cliniques à 24 mois | Non | Patients, centres, temps | Forte |

Environ 70 % du périmètre décrit (agents documentaires et de surveillance) n'offre aucune résistance [estimé : 4 lignes sur 6 du tableau, pondérées par leur place dans la description]. Toute la résistance tient dans la signature et le registre.

## 2. Scénarios de capacité

| Scénario | Ce que devient le produit | Valeur résiduelle | Qui capte la marge |
|---|---|---|---|
| (a) Modèles 2x meilleurs en 2027 | Un cabinet d'affaires réglementaires « augmenté », dont les livrables sont copiables par tout concurrent équipé | PRRC, jugement clinique, relation avec l'ON | Le client (moins d'heures facturées) et les éditeurs eQMS |
| (b) Modèles 10x, computer use fiable (2028-2029) | Les agents opèrent eux-mêmes EUDAMED, l'eQMS et Jira ; les ON automatisent aussi leur revue | Signature, données patients, présence en audit | Les ON (goulot), les détenteurs de données (hôpitaux, registres), les fournisseurs de modèles |
| (c) Agents natifs dans Microsoft 365, Atlassian, l'eQMS | La couche agent de l'idée devient une fonction de l'outil déjà payé | Ce qui est hors logiciel : signature et collecte clinique | Greenlight Guru, Ketryx, Qualio, Matrix, Atlassian |
| (d) Modèles ouverts gratuits au niveau des frontières | Les CHU et les sociétés savantes extraient eux-mêmes, en local et en hébergement HDS | Contrats d'accès aux centres, suivi longitudinal | Les propriétaires de données et les registres établis |

- **(a)** : le vrai concurrent n'est pas OpenAI mais le consultant indépendant en affaires réglementaires équipé d'un modèle, qui double sa capacité.
- **(b)** : les ON instruiront eux aussi avec des modèles, ce qui résorbe leur saturation, donc une partie de l'urgence vendue par l'idée.
- **(c)** : le plus probable à court terme. Greenlight Guru revendique plus de 1 000 entreprises clientes, une IA conversationnelle sur les données qualité et un EDC validé pour gérer un PMCF aligné sur le MDR [vérifié] (https://www.greenlight.guru/, consulté le 2026-11-03). L'éditeur eQMS couvre déjà documentation et collecte PMCF.
- **(d)** : l'argument « un agent dans chaque centre » s'inverse. Avec un modèle ouvert sur son entrepôt de données de santé, le CHU pré-remplit lui-même ses cahiers d'observation et garde la marge.

## 3. Inventaire des actifs durables revendiqués

| Actif | Réel ? | Délai de construction | Contournable par | Verdict |
|---|---|---|---|---|
| PRRC déclarée dans EUDAMED | Oui, mais non exclusif | 1 à 3 mois (recrutement d'une personne qualifiée, assurance RC) [hypothèse] | Tout cabinet, tout mandataire européen, toute CRO | Ticket d'entrée, pas un moat |
| Responsabilité portée | Oui | Immédiat (c'est un contrat) | Idem ; c'est surtout un coût | Passif autant qu'actif |
| Corpus de questions d'ON | Partiellement | 3 à 5 ans pour une masse critique [estimé] | Grands cabinets (bases de milliers de dossiers), ON eux-mêmes | Faible avant 2029 |
| Registre multi-fabricants | Oui | 36 à 42 mois jusqu'à la première donnée à 24 mois [estimé] | Sociétés savantes, CRO, éditeurs EDC | Seul vrai moat, mais occupé |
| Conventions hospitalières | Oui | 6 à 18 mois par établissement [hypothèse] | Sociétés savantes (les investigateurs sont leurs membres) | Réel, lent |
| Conformité CNIL et HDS | Oui | Semaines (hébergeur certifié) à mois | Achetable par tous | Commodité |
| Intégrations Jira, Git, eQMS | Faible | Semaines | Connecteurs MCP natifs | Nul |
| Verrouillage par la documentation | Faible | Sans objet | Le fabricant possède sa documentation technique et doit pouvoir la produire | Nul |
| Suivi longitudinal de cohortes | Oui | Le temps ne se compresse pas | Personne, une fois constitué | Le plus durable |
| Distribution (Medicen, Paris Santé Campus, Eurobiomed) | Oui | 6 à 12 mois | Tous les cabinets y sont déjà | Non exclusif |

### 3.1 La PRRC : une responsabilité réelle, un actif banal

Trois faits affaiblissent l'argument.

1. **Le prix de marché.** Un mandataire européen affiche publiquement une PRRC externe « à partir de 4 000 euros par an » [vérifié] (https://www.getear.eu/services/, consulté le 2026-11-03). L'idée vend 3 000 à 10 000 euros par mois, soit 36 000 à 120 000 euros par an, de 9 à 30 fois plus [estimé : 36 000 / 4 000 et 120 000 / 4 000]. Ce n'est donc pas la signature qui justifie le prix, mais le travail documentaire, c'est-à-dire précisément la partie que les modèles banalisent.
2. **Le périmètre légal.** La PRRC externe n'est permise qu'aux micro et petites entreprises : moins de 50 salariés et un chiffre d'affaires ou un total de bilan d'au plus 10 M€ [vérifié] (MDCG 2019-7 rev.1, https://health.ec.europa.eu/document/download/463b4f08-44a2-4018-9957-488bf386fc3a_en, consulté le 2026-11-03). La cible « 5 à 250 salariés » est donc fausse pour sa moitié haute. La qualification exigée (diplôme et un an d'expérience, ou quatre ans d'expérience) est à la portée de milliers de professionnels en Europe.
3. **La révision du MDR baisse encore la barrière.** La proposition COM(2025) 1023 du 16 décembre 2025 remplace l'exigence d'une PRRC disponible « en permanence et de façon continue » par une simple disponibilité, et allège les qualifications [vérifié] (https://www.simmons-simmons.com/en/publications/cmmm9hgom004utvk4bgvvn4ok/eu-proposes-overhaul-of-mdr-ivdr et https://www.cuatrecasas.com/en/latam/life-sciences-healthcare/art/mdr-ivdr-simplifying, consultés le 2026-11-03). Plus d'offreurs, prix plus bas.

La responsabilité est bien un point qu'aucun éditeur de modèle n'assumera. Mais n'importe quel cabinet de deux personnes l'assume déjà. Le MDCG 2019-7 ne traite pas de la responsabilité personnelle de la PRRC, qui relève du droit national : c'est un risque assurable et tarifé, pas une rente.

### 3.2 Le corpus des questions d'ON : réel, trop petit, et pas entièrement à vous

- **Volume** : 30 clients en 2028, avec une ou deux séries de questions par an, donnent 30 à 60 échanges par an [estimé], répartis entre une cinquantaine d'ON [hypothèse], plusieurs classes et des dizaines de types de dispositifs. Aucune régularité statistique avant plusieurs années.
- **Concurrence** : les grands cabinets (NAMSA, Qserve, Emergo, Johner, MDx CRO) accumulent ce savoir depuis 2017 sur des milliers de dossiers, et l'outillent avec les mêmes modèles.
- **Propriété** : les questions d'un ON sont des informations confidentielles du client. Les réutiliser exige anonymisation et clause explicite, que les clients bien conseillés refuseront.
- **Obsolescence** : la révision du MDR (certificats sans durée maximale, code de conduite obligatoire des ON, conseil scientifique formalisé) périmera une partie des précédents 2024-2027.

### 3.3 Le registre : le seul vrai moat, déjà occupé et en retard

- **Catégories occupées.** Pour le rachis, Spine Tango (EUROSPINE) existe depuis 2002. Il revendique plus de 700 hôpitaux contributeurs, plus de 160 000 chirurgies, plus de 600 000 questionnaires de résultats dans 30 pays, et une bibliothèque de plus de 200 000 implants alimentée par 75 fabricants [vérifié] (portfolio industrie v3, août 2024, https://www.eurospine.org/fileadmin/Quality_Assurance/MedTech/SPINE_TANGO_INFORMATION_INDUSTRY_PORTFOLIO_v3_August_2024_FINAL.pdf, consulté le 2026-11-03). Il vend déjà aux industriels des rapports par marque et des comparaisons entre dispositifs similaires, présentés explicitement comme une réponse aux exigences d'état de l'art du MDR. Pour la paroi abdominale, Herniamed (Allemagne, Autriche, Suisse) sert de base à des comparaisons par dispositif ; ses données, avec celles du registre danois, ont contribué au retrait de la prothèse Physiomesh [vérifié] (https://pubmed.ncbi.nlm.nih.gov/28594740/ et https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11297116/, consultés le 2026-11-03). En France, le Club Hernie recensait déjà plus de 17 700 cures inguinales et plus de 7 000 cures ventrales [vérifié, donnée ancienne, projet CORE vers 2018] (https://www.springermedizin.de/comparison-of-hernia-registries-the-core-project/15347812).
- **Prix de référence.** Spine Tango facture un abonnement annuel de 14 500, un service de rapports de 0 à 32 000 selon la taille du fabricant, et une part variable de 3,50 par procédure (devise non précisée dans le document, contrat de droit suisse) [vérifié] (même portfolio). Une PME de moins de 2 M$ de ventes d'implants paie donc environ 14 500 par an plus la part variable. L'idée vise 40 000 à 200 000 euros par an et par gamme, face à un acteur établi, médicalement légitime et 3 à 14 fois moins cher [estimé : 40 000 / 14 500 et 200 000 / 14 500].
- **Calendrier.** En comptant 12 à 18 mois pour signer les conventions, puis 24 mois de suivi, la première donnée à 24 mois arrive 36 à 42 mois après le lancement, soit vers 2030 pour un lancement début 2027 [estimé]. C'est après le 31 décembre 2027 et après le 31 décembre 2028 [vérifié] (règlement 2023/607, https://eur-lex.europa.eu/eli/reg/2023/607/oj/eng). De plus, seuls les fabricants ayant déposé une demande auprès d'un ON avant le 26 mai 2024 et signé un accord avant le 26 septembre 2024 bénéficient de ces délais : ils sont déjà en cours d'instruction et déjà accompagnés. Nuance favorable : les certificats délivrés imposent souvent des engagements PMCF, et cette demande persiste après la vague.
- **Cadre juridique sous-estimé.** Rappeler activement les patients à 6, 12 et 24 mois avec questionnaires relève vraisemblablement d'une recherche non interventionnelle de catégorie 3 (avis d'un comité de protection des personnes, MR-003), et non de la seule MR-004, réservée à la réutilisation de données [hypothèse à valider par un juriste].
- **Pourquoi maintenant, corrigé.** L'usage secondaire au titre de l'espace européen des données de santé ne s'applique qu'à partir de mars 2029 pour la plupart des catégories, et de mars 2031 pour les autres [vérifié] (https://health.ec.europa.eu/ehealth-digital-health-and-care/european-health-data-space-regulation-ehds_en, consulté le 2026-11-03). L'omnibus IA, en vigueur depuis le 27 juillet 2026, reporte au 2 août 2028 les obligations haut risque des produits de l'annexe I, dont les dispositifs médicaux [vérifié] (https://digital-strategy.ec.europa.eu/en/news/ai-omnibus-enters-force, consulté le 2026-11-03). Deux des quatre arguments du « pourquoi maintenant » jouent donc après 2028.

## 4. Tests de résistance

| Test | Résultat | Commentaire |
|---|---|---|
| « ChatGPT Enterprise + un stagiaire donnent 80 % du résultat » | **Échoue en partie** | Vrai pour la documentation, la veille et les brouillons de CER et de PSUR. Faux pour la signature (le stagiaire n'a pas la qualification de l'article 15) et pour les données cliniques. |
| « Un consultant indépendant expérimenté + Claude » | **Échoue** | Il signe comme PRRC, rédige avec un modèle et facture à la journée. C'est le concurrent le plus dangereux, et il existe par milliers. |
| « L'eQMS livre des agents natifs » | **Échoue** | Greenlight Guru (documentation, IA et EDC PMCF) et Ketryx (agents validés, MCP) le font déjà. |
| « La société savante vend l'accès registre à 15 000 par an » | **Échoue** | C'est le tarif actuel de Spine Tango. Le registre maison doit prouver une donnée que la société savante n'a pas. |
| « Le client part au bout d'un an : que perd-il ? » | **Passe en partie** | Rien côté documentation : le fabricant possède sa documentation technique. Beaucoup s'il est inscrit dans une cohorte de suivi à 24 mois en cours : c'est le seul verrou réel. |
| « La donnée arrive-t-elle avant l'échéance ? » | **Échoue** | Première donnée à 24 mois vers 2030 [estimé], contre des échéances fin 2027 et fin 2028. |
| « La révision du MDR réduit-elle l'urgence ? » | **Échoue en partie** | Certificats sans durée maximale de 5 ans, PSUR tous les 2 ans en classes IIb et III et « si nécessaire » en IIa. Texte final pas avant fin 2027 ou début 2028 [vérifié] (https://goodlifesci.sidley.com/2026/10/16/a-more-competitive-medtech-landscape-in-the-eu-what-the-mdr-ivdr-revision-could-mean-for-medtech-manufacturers-and-investors/, 16/10/2026). La demande récurrente post-2028 baisse. |

Bilan : sur sept tests, un seul passe partiellement, et uniquement pour un registre déjà constitué.

## 5. Ce qui tuerait l'idée

### 5.1 La falaise de 2028

**Scénario.** La vague de 2026-2028 passe, mais ses clients sont déjà accompagnés par leurs cabinets. La révision du MDR, adoptée vers 2028, supprime la recertification quinquennale et espace les PSUR. Le registre n'a pas encore de donnée. Le récurrent (3 000 à 10 000 euros par mois) chute pendant que le registre consomme du capital.

**Contre-mesures crédibles.** Vendre tout de suite des forfaits de remédiation à résultat (réponse à une non-conformité majeure, dossier clinique remis à niveau) plutôt qu'un abonnement. Ancrer le récurrent sur les obligations qui survivent à la révision (vigilance, PMS, engagements PMCF inscrits dans les certificats). Ne pas financer un registre propre avant un premier contrat fabricant signé.

### 5.2 L'incident grave chez un client

**Scénario.** Un implant de classe III d'un client provoque des incidents graves. L'ANSM enquête, la PRRC externe est mise en cause, l'assureur RC résilie ou triple la prime, et les autres clients partent. Pour une équipe de 2 à 6 personnes, un seul dossier suffit.

**Contre-mesures crédibles.** Exclure les classes III et IIb implantables du périmètre PRRC pendant les deux premières années. Limiter l'offre aux logiciels dispositifs médicaux et aux classes IIa et IIb non implantables. Porter la PRRC dans une entité juridique distincte. Refuser à l'entrée les clients dont le système qualité est jugé faible. Tracer chaque acte de vérification de la PRRC.

### 5.3 Les centres disent non, ou disent oui à quelqu'un d'autre

**Scénario.** Les directions de la recherche clinique refusent un agent tiers sur le dossier patient. Les sociétés savantes (EUROSPINE, Club Hernie, orthopédie) voient un concurrent et ferment l'accès à leurs investigateurs, puis signent avec un éditeur EDC ou une CRO. Le premier registre n'atteint jamais la taille critique.

**Contre-mesures crédibles.** Devenir l'infrastructure des registres existants plutôt que leur concurrent : offrir aux sociétés savantes l'agent de pré-remplissage, qui améliore l'exhaustivité de la saisie (leur point faible chronique), contre des droits d'exploitation partagés. Ne créer un registre propre que dans une catégorie sans registre établi.

## 6. Verdict adverse

### 6.1 Note : 4/10 pour l'idée telle que formulée

La résistance aux LLM est réelle sur deux actifs seulement : la signature d'une personne qualifiée et la donnée clinique longitudinale. Le premier n'a aucune rareté : il s'achète à 4 000 euros par an, la révision l'ouvre davantage, et tout concurrent équipé d'un modèle le propose. Le second est rare, mais trois facteurs en privent l'entreprise : des registres de sociétés savantes déjà installés, plusieurs fois moins chers ; un délai de 36 à 42 mois qui manque les échéances ; des centres capables d'extraire eux-mêmes avec des modèles ouverts. Le reste du périmètre, soit l'essentiel du travail des agents, est absorbé par les modèles 2x de 2027 et par les éditeurs eQMS. La note n'est pas plus basse car la signature maintient un plancher de service et un registre réussi serait quasi impossible à rattraper.

### 6.2 Version la plus résistante : opérateur de collecte PMCF pour registres existants

**Pivot recommandé.** Faire du produit l'infrastructure de collecte des registres cliniques existants, et non un registre concurrent ni une PRRC généraliste.

- **Cœur** : un agent installé chez le CHU, ou chez l'hébergeur certifié du registre, qui pré-remplit les cahiers d'observation à partir du dossier patient et des comptes rendus opératoires, relie chaque valeur à sa source et gère les relances de suivi. Il est vendu aux sociétés savantes ou co-exploité avec elles. L'actif durable est la position contractuelle dans le flux hospitalier et l'historique de cohortes qu'elle alimente. Le temps ne se compresse pas, quelle que soit la puissance des modèles.
- **Monétisation fabricant** : des paquets de données PMCF prêts pour l'ON (état de l'art comparatif, rapport PMCF) produits à partir de ces registres, en partage de revenus avec la société savante.
- **PRRC et rédaction** : produit d'appel et de trésorerie, réservé aux micro et petites entreprises, aux logiciels dispositifs médicaux et aux classes IIa et IIb non implantables. C'est aussi le segment où l'IA multiplie les nouveaux fabricants soumis au MDR et à l'AI Act à partir du 2 août 2028.

**Note de la version pivotée : 6/10.** La rareté vient alors de l'accès légal et organisationnel aux données des centres, et de la profondeur temporelle des cohortes : un modèle 10x ne fabrique ni l'un ni l'autre. Le risque principal se déplace vers l'exécution : convaincre au moins une société savante dans les 12 premiers mois. Faute de ce partenariat, l'idée doit être abandonnée plutôt que poursuivie sous sa forme documentaire, qui ne résiste pas.

## Sources

Toutes consultées le 2026-11-03, sauf mention contraire.

- MDCG 2019-7 rev.1, PRRC (article 15 MDR et IVDR) : https://health.ec.europa.eu/document/download/463b4f08-44a2-4018-9957-488bf386fc3a_en
- Règlement (UE) 2023/607 : https://eur-lex.europa.eu/eli/reg/2023/607/oj/eng
- Proposition COM(2025) 1023 (16/12/2025) : https://www.simmons-simmons.com/en/publications/cmmm9hgom004utvk4bgvvn4ok/eu-proposes-overhaul-of-mdr-ivdr ; https://www.cuatrecasas.com/en/latam/life-sciences-healthcare/art/mdr-ivdr-simplifying
- Calendrier législatif de la révision (Sidley, 16/10/2026) : https://goodlifesci.sidley.com/2026/10/16/a-more-competitive-medtech-landscape-in-the-eu-what-the-mdr-ivdr-revision-could-mean-for-medtech-manufacturers-and-investors/ ; https://dsv-europa.de/en/news/2026/07/mdr-ivdr.html
- Omnibus IA (entrée en vigueur le 27/07/2026) : https://digital-strategy.ec.europa.eu/en/news/ai-omnibus-enters-force
- Espace européen des données de santé, calendrier : https://health.ec.europa.eu/ehealth-digital-health-and-care/european-health-data-space-regulation-ehds_en
- Tarifs PRRC externe et mandataire (getEAR) : https://www.getear.eu/services/
- Spine Tango, portfolio industrie v3 (août 2024) : https://www.eurospine.org/fileadmin/Quality_Assurance/MedTech/SPINE_TANGO_INFORMATION_INDUSTRY_PORTFOLIO_v3_August_2024_FINAL.pdf ; https://www.eurospine.org/spine-tango.htm
- Registres de hernie (projet CORE) : https://www.springermedizin.de/comparison-of-hernia-registries-the-core-project/15347812 ; Herniamed : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11297116/ ; https://pubmed.ncbi.nlm.nih.gov/28594740/
- Chen X., Zhang X., « Large language models streamline automated systematic review » (janvier 2025) : https://arxiv.org/abs/2502.15702
- Flinn, série A (19/02/2026) : https://tech.eu/2026/02/19/flinn-secures-20m-to-develop-ai-tools-for-product-lifecycle-management-in-medtech-and-pharma/
- Ketryx, levées et agents : https://www.ketryx.com/news
- Greenlight Guru, IA et EDC PMCF : https://www.greenlight.guru/
- Team-NB, position sur l'AI Act (2025) : https://team-nb.org/wp-content/uploads/2025/02/Team-NB-PositionPaper-Artificial-Intelligence.pdf
