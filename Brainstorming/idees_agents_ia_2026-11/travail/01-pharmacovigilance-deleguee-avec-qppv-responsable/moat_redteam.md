# Pharmacovigilance déléguée avec QPPV responsable : Moat et résistance aux LLM (red team)

Périmètre : ce chapitre attaque la thèse de défendabilité de l'idée C01, puis isole ce qui tient. Le dimensionnement du marché, la cartographie concurrentielle et le modèle économique relèvent d'autres chapitres ; ils ne sont mobilisés ici que lorsqu'ils conditionnent le moat. Les renvois [S1] à [S19] pointent vers le tableau des sources en fin de chapitre (URL et dates).

## Synthèse adverse

- **Ce qui résiste.** Le droit européen exige une personne physique qualifiée, résidant et exerçant dans l'Union, joignable en permanence et déclarée à l'EMA [S5] ; la France ajoute un RPV médecin ou pharmacien exerçant en France [S6]. Aucun éditeur de modèle ne tiendra ce rôle. La demande pour le service est durable.
- **Ce qui ne résiste pas.** La couche agentique est déjà livrée par les éditeurs de bases de sécurité et par des start-up financées ; la mutualisation des données entre génériqueurs duplique un bien public gratuit ; l'historique d'inspection est un actif des sortants, pas de l'entrant.
- **Le point aveugle.** La responsabilité du QPPV n'est pas exclusive : chaque CRO, chaque boutique française et chaque QPPV indépendant la vend. Elle protège contre OpenAI, pas contre un concurrent équipé des mêmes agents. Juridiquement, le titulaire d'AMM conserve d'ailleurs l'entière responsabilité de son système, même sous-traité [S7] : le prestataire fournit un nom, il ne reprend pas la responsabilité du titulaire.
- **Deux prémisses de la fiche sont fausses.** Les volumes d'ICSR ne croissent pas de 10 % par an : +0,5 % en 2025 dans EudraVigilance [S1] [vérifié]. Les PSUR, mis en avant, concernent peu la cible : génériques, usage bien établi, homéopathie et phytothérapie traditionnelle en sont exemptés hors liste EURD [S8] [vérifié].
- **Note de résistance aux LLM : 5/10.** Le besoin survit à des modèles 10x meilleurs ; la marge de l'entrant, non, sauf pivot (section 6).

## 1. Faisabilité technique aujourd'hui

### 1.1 Ce qui fonctionne déjà

| Tâche | État fin 2026 | Fiabilité | Sources |
|---|---|---|---|
| Extraction d'un signalement (e-mail, PDF, formulaire), triage, relances | Produits commerciaux : Veeva Falcon Safety (annonce du 1er septembre 2026, accès anticipé en novembre 2026, compatible avec toute base E2B dont Argus et LifeSphere), IQVIA Vigilance Intake, Graph AI | Élevée sur des déclarations de professionnels de santé | [S2] [S3] [S4] [vérifié] |
| Codage MedDRA de termes cliniques propres | 86,7 % à 90,2 % d'exactitude au niveau HLT avec un LLM outillé (système ALIGN, RAG) | Élevée, sous revue humaine | [S9] [vérifié] |
| Codage MedDRA de verbatims de patients | Tâche partagée ALTA 2025 : 35 % à 40 % d'exactitude au premier rang pour les meilleurs systèmes, environ 78 % dans les 5 premières propositions | Faible sans humain | [S10] [vérifié] |
| Narration, brouillon de rapport agrégé, criblage bibliographique | Fonction standard des offres 2026 (agent de narration de Veeva, module /report de Graph AI) | Bonne en brouillon relu | [S2] [S4] [vérifié] |
| Causalité, décision de signal | Recherche ; le CIOMS XIV réserve ces jugements aux experts humains | Supervisée uniquement | [S11] [vérifié] |

Les gains annoncés sont massifs mais déclaratifs : Graph AI revendique un traitement de cas ramené de plus de 3 heures à moins de 10 minutes et jusqu'à 66 % de coûts opérationnels en moins [S4] ; IQVIA annonce 30 % à 50 % de réduction de coûts sur la réception [S3] ; Tech Mahindra et NVIDIA annoncent des délais réduits de 40 % [S3]. [vérifié quant à l'annonce, performance non auditée]

### 1.2 Ce qui échoue encore

- **Spécificité et hallucinations.** Une revue systématique de 83 études (Diagnostics, août 2026) relève une sensibilité élevée mais une spécificité faible, des affirmations causales inventées, une forte dépendance au libellé du prompt et une reproductibilité médiocre. Elle conclut que les preuves ne soutiennent que des usages supervisés et ciblés [S12] [vérifié].
- **Le faux négatif silencieux.** Le risque n'est pas le codage, c'est la reconnaissance qu'un appel, un message de partenaire ou une réclamation qualité contient un cas valide, et la datation du jour 0. Un cas raté ne laisse aucune trace jusqu'à la réconciliation ou l'inspection. Or depuis décembre 2025, l'EMA envoie automatiquement à chaque émetteur un rapport de conformité aux délais de déclaration [S1] [vérifié] : chaque retard est désormais mesuré en continu, par le régulateur comme par le client.
- **Validation contre cadence des modèles.** Dans un système validé (GAMP 5, Annexe 11), changer de version de modèle déclenche une maîtrise des changements et une revalidation. Les modèles de pointe changent tous les 3 à 6 mois [hypothèse]. L'entreprise doit soit figer un modèle ancien, ce qui contredit la thèse « chaque progrès des modèles augmente la marge », soit financer une revalidation permanente.
- **Actions irréversibles.** Une transmission E2B à EudraVigilance peut être annulée, mais l'annulation est tracée et le délai de 15 ou 90 jours reste compté.

### 1.3 Ce que cela implique pour la promesse

La promesse « usine à cas » est techniquement atteignable dès 2026. C'est précisément pour cela qu'elle ne différencie pas : la même automatisation atteindra les CRO par leurs éditeurs en 12 à 24 mois [hypothèse]. Pour la cible, à faibles volumes, le traitement de cas pèse peu : un titulaire recevant 200 cas par an passe d'environ 600 heures de traitement (3 heures par cas) à environ 33 heures (10 minutes par cas) [estimé : volume de 200 cas hypothétique, durées issues de S4]. Ce qui reste incompressible est un coût fixe : supervision du QPPV, système qualité, audits, PSMF, préparation des inspections. Le produit converge vers un service de responsabilité, pas vers un logiciel.

## 2. Scénarios de capacité

| Scénario | Ce que devient le produit | Valeur restante | Qui capte la marge |
|---|---|---|---|
| (a) Modèles 2x meilleurs en 2027 | Les cas de professionnels de santé passent quasiment sans retouche. CRO et boutiques adoptent Falcon, Graph AI ou leurs outils maison. Guerre des prix sur les forfaits. | Intacte en volume, en baisse en prix. L'avance de l'entrant tient 12 à 18 mois [hypothèse]. | L'entrant transitoirement, puis l'éditeur de la base et le client. |
| (b) Modèles 10x, computer use fiable (2028-2029) | Un agent pilote EVWEB (l'interface web de l'EMA pour créer et transmettre des ICSR), le portail ANSM, la boîte PV et les bases bibliographiques. Un micro-titulaire assemble lui-même : base SaaS, agent, QPPV indépendant à la journée. La chaîne se coupe en deux : logiciel et signature humaine. | Le temps du QPPV, sa signature et la défense en inspection. | Les éditeurs (logiciel) et les QPPV rares (travail). L'intermédiaire est pris en étau. |
| (c) Agents génériques natifs dans les plateformes dominantes | L'« ERP » de la verticale n'est ni SAP ni Salesforce mais Veeva Vault, Argus et LifeSphere. Veeva livre déjà les agents de réception et de narration au système d'enregistrement, pour des biopharmas « de toutes tailles » [S2]. Copilot ou Gemini trient la boîte PV des petits laboratoires dans Outlook ou Gmail, sans pouvoir servir de base validée. | La pile d'agents de l'entrant ne vaut plus rien. Reste le service humain responsable, que Veeva ne vend pas, mais que ses partenaires CRO vendent. | Veeva et ses partenaires de services. |
| (d) Modèles ouverts gratuits au niveau de la frontière | Inférence quasi gratuite, hébergeable en France (données de santé, RGPD). Les modèles ouverts suivent la frontière avec 5 à 22 mois de retard [S13] [vérifié, donnée 2024]. | Aucun avantage technologique pour personne. | Le détenteur de la clientèle et de la responsabilité : le gain revient d'abord aux sortants, qui ont déjà les clients. |

La thèse « le prix suit le périmètre, donc le progrès des modèles devient de la marge » ne tient que si les concurrents ne répercutent pas leurs gains. Or le marché est dense, et Tepsivo (Helsinki) se positionne déjà à « environ 30 % du prix de marché » grâce à un logiciel maison et à l'IA, avec un forfait complet de 60 000 à 100 000 euros par an pour une petite organisation [S14] [vérifié, tarif public]. Le prix au périmètre se cale alors sur le coût du QPPV et de l'assurance, pas sur la valeur perçue. Le gain de marge est réel, mais transitoire.

## 3. Inventaire des actifs revendiqués

| Actif revendiqué | Réel ? | Délai de construction | Contournable ? Par qui ? |
|---|---|---|---|
| Rôle de QPPV nommé dans le PSMF et dans la base article 57 | Réel contre les éditeurs de modèles. Non exclusif : c'est le rôle d'une personne physique, que tout prestataire fournit. Le titulaire garde l'entière responsabilité [S7]. | Immédiat si un QPPV cofonde ; impossible sinon. | Oui : CRO, boutiques françaises (Pharmya, Atessia Vigilances), QPPV indépendants, Tepsivo [S14] [S15]. |
| RPV France (médecin ou pharmacien exerçant en France) | Réel, petite barrière face aux acteurs étrangers [S6]. | Immédiat. | Oui : Tepsivo vend un contact local à 600 euros par mois et par pays [S14] [vérifié]. |
| Base de sécurité validée et historique des cas | Réel : la migration validée crée un coût de sortie. | 6 à 12 mois de validation [hypothèse]. | En partie : l'export E2B(R3) est standard, et les agents réduiront eux-mêmes le coût des migrations. Ce moat s'érode avec le progrès des modèles. |
| Données mutualisées par substance entre génériqueurs | Largement illusoire. Les cas appartiennent à chaque titulaire (confidentialité contractuelle, RGPD article 9). EudraVigilance contient déjà 31,2 millions d'ICSR [S1] [vérifié] ; le service MLM de l'EMA couvre 309 groupes de substances actives et 100 groupes de substances végétales [S16] [vérifié, périmètre 2020]. | Plusieurs années, sans exclusivité. | Oui : par l'EMA, gratuitement. |
| Détection de signaux propriétaire | Faible. L'EMA a examiné 1 201 signaux potentiels portant sur 995 substances en 2025. Sur 61 signaux notifiés par des titulaires entre 2018 et 2025, 13 étaient valides et 1 a été confirmé ; le règlement d'exécution (UE) 2025/1466 a supprimé ces notifications [S1] [vérifié]. | Sans objet. | Oui : par le régulateur. |
| Historique d'inspections sans constat critique | Réel, mais il profite aux sortants. Une start-up n'en a aucun pendant plusieurs années, car les inspections sont rares : 17 inspections GPvP par la MHRA en 2022/2023, dont 4 constats critiques [S17] [vérifié, source secondaire]. | 3 à 6 ans [hypothèse]. | Non contournable, mais il joue contre l'entrant. |
| Effets de réseau | Inexistants entre clients (données cloisonnées). | Sans objet. | Sans objet. |
| Distribution (pharmaciens responsables, GEMME, AFIPA, Synadiet) | Réel, relationnel, réplicable. | 2 à 4 ans [hypothèse]. | Oui : toute boutique installée. |
| Pile d'agents | Non durable. | Environ 6 mois [hypothèse]. | Oui : Veeva, IQVIA, Graph AI, Tech Mahindra [S2] [S3] [S4]. |

Ce tableau inverse la thèse : les actifs propres à l'entrant (agents, données mutualisées, signaux) sont les plus faibles ; le seul actif fort, la signature du QPPV, n'appartient pas à l'entreprise mais à une personne qui peut partir.

## 4. Tests de résistance

| Test | Résultat | Mécanisme |
|---|---|---|
| ChatGPT Enterprise et un stagiaire obtiennent-ils 80 % du résultat ? | Passé | Oui pour 80 % de la rédaction. Mais le client n'achète pas du texte : il lui faut un QPPV déclaré, un système et un PSMF inspectables, une joignabilité 24 heures sur 24. Le stagiaire n'apporte rien de cela. |
| Assistant IA d'entreprise, QPPV indépendant 2 jours par mois, EVWEB ou base SaaS | Échoué pour les micro-portefeuilles | Pour un titulaire de 1 à 5 produits, cet assemblage livre l'essentiel pour un coût proche du bas de la grille visée (1 500 euros par mois) [hypothèse]. Le scénario (b) le rend banal. |
| Un sortant peut-il répliquer l'offre en 12 mois ? | Échoué | Il lui suffit d'acheter Falcon Safety ou Graph AI ; il a déjà les QPPV, les clients et l'historique d'inspection. |
| Le prix tient-il quand le coût baisse ? | Échoué à moyen terme | Marché dense, acteur à bas prix déjà installé [S14]. |
| Le régulateur accepte-t-il un QPPV signant pour des dizaines de titulaires très automatisés ? | Incertain | Le document de réflexion de l'EMA (30 septembre 2024) exige une approche centrée sur l'humain et fondée sur le risque [S19] ; le CIOMS XIV met en garde contre une automatisation guidée par les seuls objectifs financiers [S11] ; le règlement 2025/1466, applicable depuis le 12 février 2026, impose des contrats précisant rôles, audits et limites de sous-traitance [S18]. Le nombre de clients par QPPV devient à la fois un plafond de croissance et un point d'inspection. |
| Le vent porteur des volumes existe-t-il ? | Échoué | 1 765 581 ICSR en 2025, soit +0,5 % ; cas non graves -5 % ; déclarations de patients -11 % [S1] [vérifié]. |
| Les agents créent-ils beaucoup de valeur sur la cible ? | Échoué en partie | PSUR de routine exemptés pour les génériques, l'usage bien établi, l'homéopathie et la phytothérapie traditionnelle [S8] ; littérature déjà couverte par le MLM pour les substances les plus génériquées [S16]. |

L'idée survit donc au test « ChatGPT et un stagiaire », mais échoue aux tests qui comptent : ceux où l'adversaire est un concurrent humain équipé des mêmes modèles.

## 5. Trois scénarios de mort et contre-mesures

### Mort n°1 : le constat critique systémique

Un agent de réception classe en « non-cas » une catégorie entière de messages, par exemple les réclamations qualité qui mentionnent un effet indésirable, ou les messages de partenaires en langue étrangère. Le défaut est systématique : il touche en même temps tous les clients qui partagent le même QPPV et la même chaîne. Une inspection de l'ANSM chez un client le révèle ; les autres clients lisent leurs rapports de conformité EMA et déclenchent leurs audits. Dans un modèle mutualisé, le risque n'est pas indépendant d'un client à l'autre : il est corrélé.

Contre-mesures : revue humaine de 100 % des classements « non-cas » pendant 24 mois, puis échantillonnage statistique documenté ; règle conservatrice (dans le doute, c'est un cas) ; réconciliation mensuelle avec les rapports de conformité de l'EMA ; tests de régression sur un corpus de référence à chaque changement de modèle ; assurance responsabilité civile professionnelle dimensionnée sur le pire cas.

### Mort n°2 : la compression des prix

Entre fin 2026 et 2028, Veeva Falcon passe en disponibilité générale, Graph AI (13,3 millions de dollars levés en série A en septembre 2026 [S4] [vérifié]) équipe les CRO, et les boutiques françaises s'outillent. La remise de 40 % à 60 % sur les CRO devient le prix de marché. Avec deux QPPV, la société plafonne : à 15 clients par QPPV et 3 000 euros par mois en moyenne, deux QPPV portent environ 1,1 million d'euros de revenu annuel [estimé : 2 x 15 x 3 000 x 12 ; ratio et prix moyen hypothétiques]. C'est une bonne boutique, pas une entreprise qui monte en échelle.

Contre-mesures : se placer là où les sortants ne vont pas (micro-titulaires, importateurs parallèles, phytothérapie, rachats de portefeuille) ; vendre un engagement de résultat plutôt qu'un forfait ; recruter des QPPV seniors avec une part du capital pour desserrer le plafond.

### Mort n°3 : la personne clé

Le QPPV cofondateur part, tombe malade ou refuse de signer pour un taux d'automatisation qu'il ne maîtrise plus. Chaque client doit mettre à jour son PSMF et la base article 57 ; beaucoup en profitent pour revenir vers un prestataire installé. Variante en amont : aucun QPPV senior n'accepte d'engager son nom, et l'entreprise ne démarre jamais.

Contre-mesures : deux QPPV seniors dès le lancement (titulaire et suppléant) ; pacte d'associés avec clauses de transition ; procédures écrites qui protègent le QPPV (ce que l'agent décide, ce qu'il ne décide jamais) ; assurance homme-clé.

## 6. Verdict adverse

### Note de résistance aux LLM : 5/10

Mécanisme : l'obligation de désigner une personne physique responsable, résidant dans l'Union et inspectable, ne s'automatise pas ; elle garantit que la demande survit aux quatre scénarios. Mais cet actif est générique, détenu par tous les prestataires et attaché à une personne, pas à l'entreprise. Les actifs propres à l'entrant (agents, données mutualisées, détection de signaux) sont soit banalisés par les éditeurs, soit fournis gratuitement par l'EMA. Le progrès des modèles fait baisser le coût de tous les acteurs puis, par la concurrence, le prix. La note combine un besoin quasi indestructible (8/10) et une position concurrentielle de l'entrant fragile (3/10).

### Version la plus résistante (pivot recommandé)

1. **Abandonner trois arguments** : la mutualisation des données entre clients, la détection de signaux propriétaire et la croissance des volumes. Aucun ne résiste à une diligence sérieuse.
2. **Racheter l'historique au lieu de le construire.** Acquérir une boutique française existante (10 à 30 clients, un QPPV ayant déjà traversé plusieurs inspections) ou s'y adosser, puis y greffer les agents. L'historique d'inspection s'achète ; il ne se fabrique pas en moins de 3 ans.
3. **Se spécialiser sur le jour 1** : nouvelles AMM, rachats et transferts de portefeuille, départs de QPPV. Reprise du PSMF, migration et réconciliation de cas hétérogènes en 30 jours. C'est le cas d'usage où les LLM donnent un vrai avantage de vitesse (données sales, multilingues) et où l'urgence du client écrase la sensibilité au prix.
4. **Vendre un engagement de conformité, pas un forfait** : pénalités contractuelles en cas de retard imputable au prestataire, adossées à un assureur. Un prestataire payé au temps passé ne peut pas suivre ; un agent générique ne peut pas l'offrir.
5. **Viser l'Europe des micro-titulaires** avec un réseau de contacts locaux et une veille de la littérature locale hors MLM dans les langues de l'Union [S16] : une obligation réelle, mal servie, où les LLM excellent et où le prix par pays reste bas.

Ainsi recadrée, l'idée vaudrait 6 à 7/10 : la signature humaine reste le produit, l'IA devient la structure de coûts, et l'actif défendable devient une réputation d'inspection rachetée et un engagement de résultat assuré.

## Sources

| ID | Source | URL | Date |
|---|---|---|---|
| S1 | EMA, 2025 Annual Report on EudraVigilance (EMA/371010/2025) | https://www.ema.europa.eu/en/documents/report/2025-annual-report-eudravigilance-european-parliament-council-commission_en.pdf | Publié en 2026, consulté le 2026-11-03 |
| S2 | Veeva Systems, communiqué Falcon Safety ; Unite.ai | https://www.veeva.com/resources/veeva-falcon-safety-to-work-with-all-e2b-compliant-safety-systems-across-any-intake-channels/ ; https://www.unite.ai/veeva-falcon-safety-automates-adverse-event-intake-across-e2b-systems/ | 2026-09-01, consulté le 2026-11-03 |
| S3 | IQVIA Vigilance Intake ; Tech Mahindra et NVIDIA | https://www.iqvia.com/solutions/safety-regulatory-compliance/safety-and-pharmacovigilance/iqvia-vigilance-platform/iqvia-vigilance-intake ; https://biospectrumindia.com/news/16/25856/tech-mahindra-and-nvidia-collaborate-to-advance-drug-safety-using-agentic-ai.html | Consulté le 2026-11-03 |
| S4 | Graph AI, communiqué de série A (PR Newswire) | https://www.prnewswire.com/news-releases/graph-ai-raises-13-3m-series-a-to-scale-the-first-ai-native-operating-system-for-patient-safety-302874459.html | 2026-09-10, consulté le 2026-11-03 |
| S5 | EMA, GVP Module I (présentation) ; règlement d'exécution (UE) 520/2012 | https://www.ema.europa.eu/documents/presentation/presentation-guideline-good-pharmacovigilance-practices-gvp-module-i-pharmacovigilance-systems-their_en.pdf ; https://www.legislation.gov.uk/eur/2012/520/chapter/II/section/2/data.htm | Consulté le 2026-11-03 |
| S6 | ANSM, déclaration de la personne de référence en pharmacovigilance (RPV) | https://ansm.sante.fr/vos-demarches/industriel/declarer-la-personne-de-reference-en-matiere-de-pharmacovigilance-en-france-rpv | Consulté le 2026-11-03 |
| S7 | MHRA Inspectorate, accords avec les prestataires de PV ; règlement 520/2012 | https://mhrainspectorate.blog.gov.uk/2018/01/22/mhra-gpvp-inspectorate-guide-to-marketing-authorisation-holder-considerations-for-agreements-with-pharmacovigilance-system-service-providers/ | 2018-01-22, consulté le 2026-11-03 |
| S8 | EMA, GVP Module VII (PSUR) ; BASG, FAQ pharmacovigilance | https://www.ema.europa.eu/en/documents/presentation/presentation-good-pharmacovigilance-practice-module-vii-periodic-safety-update-report_en.pdf ; https://basg.gv.at/en/companies/pharmacovigilance/faqs-pharmacovigilance | Consulté le 2026-11-03 |
| S9 | ALIGN, codage MedDRA par LLM (arXiv 2411.13163) | https://arxiv.org/pdf/2411.13163 | 2024, consulté le 2026-11-03 |
| S10 | Actes ALTA 2025, normalisation MedDRA d'événements indésirables | https://aclanthology.org/2025.alta-main.16 | 2025, consulté le 2026-11-03 |
| S11 | CIOMS, rapport du groupe de travail XIV sur l'IA en pharmacovigilance | https://cioms.ch/working_groups/working-group-xiv-artificial-intelligence-in-pharmacovigilance/ | Publié le 2025-12-04, consulté le 2026-11-03 |
| S12 | Revue systématique, LLM et pharmacovigilance, Diagnostics (Basel) | https://pmc.ncbi.nlm.nih.gov/articles/PMC13465311/ | 2026-08-01, consulté le 2026-11-03 |
| S13 | Epoch AI, How Far Behind Are Open Models? | https://epoch.ai/blog/open-models-report | 2024-11-04, consulté le 2026-11-03 |
| S14 | Tepsivo, grille tarifaire publique | https://www.tepsivo.com/pricing/ | Consulté le 2026-11-03 |
| S15 | Pharmya ; Atessia Vigilances | https://www.pharmya.com/pharmacovigilance-externalisee-un-soutien-fiable/ ; https://atessiavigilances.com/responsable-de-pharmacovigilance-rpv-definition/ | Consulté le 2026-11-03 |
| S16 | EMA, Medical Literature Monitoring | https://www.ema.europa.eu/en/human-regulatory-overview/post-authorisation/pharmacovigilance-post-authorisation/medical-literature-monitoring | Périmètre de juin 2020, consulté le 2026-11-03 |
| S17 | QbD Group, synthèse des métriques d'inspection GPvP de la MHRA 2022/2023 | https://info.qbdgroup.com/en/blog/mhra-good-pharmacovigilance-practice-inspection-metrics-and-findings | Consulté le 2026-11-03 |
| S18 | UBC, analyse du règlement d'exécution (UE) 2025/1466 | https://ubc.com/insights/eu-post-marketing-compliance-what-regulation-2025-1466-means-for-your-pharmacovigilance-program/ | Consulté le 2026-11-03 |
| S19 | NSF, document de réflexion de l'EMA sur l'IA dans le cycle de vie du médicament | https://www.nsf.org/life-science-regulatory-news/ema-reflection-paper-on-ai-in-the-medicinal-product-lifecycle | Document EMA du 2024-09-30, consulté le 2026-11-03 |
