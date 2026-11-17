# Pharmacovigilance déléguée avec QPPV responsable : Clients, prix et go-to-market

**Points clés du chapitre**

- **Un vivier français étroit.** 173 PME et ETI détiennent au moins une AMM de prescription [S1, vérifié], auxquelles s'ajoutent des laboratoires OTC, de phytothérapie et des importateurs parallèles. Atteindre 100 clients impose de sortir de France dès la troisième année.
- **Un prix qui ne différencie pas.** Tepsivo, prestataire outillé par l'IA, facture déjà 60 à 100 k€ par an l'externalisation complète d'une petite structure et revendique 30 % du prix du marché [S3, vérifié]. La fourchette visée (18 à 72 k€ par an) n'est donc pas un avantage. L'argument doit être la conformité garantie par un QPPV francophone nommé.
- **Une alternative interne coûteuse.** Une PV internalisée coûte 250 à 340 k€ par an [estimé] : l'externalisation est rentable dès le premier produit.
- **Une marge qui se joue sur les heures humaines.** L'inférence coûte environ 1 k€ par client et par an, moins de 3 % du chiffre d'affaires [estimé]. Le coût dépend du temps du QPPV, de la revue médicale et de la revalidation à chaque changement de modèle.
- **Un système auditable avant la première vente.** Depuis le 12 février 2026, le règlement d'exécution (UE) 2025/1466 encadre l'audit des sous-traitants PV [S7, vérifié].

## 1. Profil de client idéal et personas

### 1.1 Vivier et ICP

- **France, prescription.** Le panorama AMLIS 2024 recense 173 entreprises (au plus 2 500 salariés et 750 M€ de chiffre d'affaires), soit 24 500 salariés et 11,1 Md€. Elles commercialisent 4 040 des 10 552 AMM présentes en France et ont obtenu 142 nouvelles AMM entre 2022 et 2024 [S1, vérifié].
- **France, hors AMLIS.** Laboratoires OTC ou de phytothérapie purs, importateurs parallèles et petites filiales étrangères : 80 à 150 entités [hypothèse].
- **ICP France.** Le vivier compte 250 à 320 titulaires. Sans les structures dotées d'une PV interne solide ou centralisée par un groupe, l'ICP strict compte 120 à 180 comptes [estimé, 50 à 60 % du vivier].
- **Europe.** 1 174 titulaires (au niveau du siège) ont transmis des ICSR à EudraVigilance en 2025 [S2, vérifié]. Ce chiffre omet les titulaires sans aucun cas dans l'année.

| Segment | Profil | Déclencheur | Cas par an [hypothèse] | Priorité |
|---|---|---|---|---|
| OTC et phytothérapie | 10 à 100 salariés, 3 à 15 substances anciennes | départ du QPPV, fin de contrat CRO | 20 à 150 | 1 : cycle court, risque faible |
| Génériqueurs et importateurs parallèles | 20 à 500 salariés, 20 à 200 AMM | rachat de portefeuille, constat d'inspection | 100 à 1 000 | 1 : volume, données mutualisables |
| Biotech en lancement | 1 ou 2 substances nouvelles, plan de gestion des risques | nouvelle AMM | 50 à 500 | 2 : panier et risque élevés |
| Exploitants pour compte de tiers | exploitent des AMM de titulaires étrangers | nouveaux mandats | variable | canal plutôt que client |

### 1.2 Personas

| Persona | Qui | Douleur quantifiée | Ce qu'il achète |
|---|---|---|---|
| **Décideur** | Pharmacien responsable, directeur général ou directeur réglementaire | Un QPPV interne coûte 102 k€ brut en moyenne en Île-de-France (75 à 150 k€) [S4, vérifié], 85 à 95 k€ pour un poste senior à Paris [S5, vérifié], soit environ 148 k€ chargés [estimé, charges de 45 %]. Pendant une vacance de poste, la non-conformité est immédiate. | Un nom inscrit dans le PSMF dès le premier jour, un suppléant, la continuité |
| **Utilisateur** | Responsable PV France ou chargé de PV | Environ 90 minutes par ICSR en traitement manuel [S6, hypothèse], soit 450 h par an pour 300 cas [estimé]. Veille hebdomadaire de toute substance hors des 309 groupes actifs et 100 groupes végétaux couverts par l'EMA [S8, vérifié]. En 2025, les titulaires ont tenu le délai de 15 jours pour 96,9 % des cas graves, mais celui de 90 jours pour seulement 80,4 % des cas non graves ; l'EMA leur envoie des notifications de conformité depuis décembre 2025 [S2, vérifié]. | Des délais tenus, moins de saisie, un tableau de bord |
| **Bloqueurs** | Assurance qualité, DPO ou DSI, QPPV ou CRO en place | Un constat critique imputable au fournisseur entraîne des actions correctives et une réinspection. Le défaut de déclaration est passible de 150 000 € d'amende pénale au plus [S9, vérifié]. | Un dossier de validation, un audit trail, un droit d'audit, un plan de réversibilité |

**Un risque surtout réputationnel.** En 2025, l'ANSM a prononcé 6 sanctions financières, toutes pour des ruptures de stock, pour 754 727 € au total [S10, vérifié]. Le discours commercial doit donc viser la réussite des inspections et des audits des partenaires, plutôt que l'évitement des amendes.

## 2. Processus d'achat

### 2.1 Décision et budget

- **Qui décide.** Le pharmacien responsable et le directeur général ; dans une biotech, le CEO et le directeur réglementaire.
- **Sur quel budget.** Le budget de fonctionnement « affaires pharmaceutiques » ou « qualité ». L'offre remplace le plus souvent une ligne existante (contrat CRO ou salaire interne). Une nouvelle AMM est financée par le budget de lancement.
- **Qui valide.** L'assurance qualité (audit fournisseur), le DPO (contrat de sous-traitance, article 28 du RGPD) et la direction financière (engagement de 3 ans).

### 2.2 Cycle de vente selon le déclencheur

| Déclencheur | Urgence | Cycle [hypothèse] | Particularité |
|---|---|---|---|
| Départ du QPPV interne | forte | 1 à 3 mois | QPPV intérimaire, puis contrat |
| Nouvelle AMM ou rachat de portefeuille | forte | 2 à 4 mois | QPPV et PSMF exigés dès le transfert |
| Constat d'inspection | moyenne | 3 à 6 mois | les actions correctives conduisent souvent à changer de prestataire |
| Renouvellement du contrat CRO | faible | 6 à 12 mois | appel d'offres privé, migration validée |

Début novembre 2026, au moins trois postes de QPPV ou de responsable PV étaient ouverts sur France Travail à Paris et Lyon [S5, vérifié] : un signal de tension sur ce recrutement, et une source de prospects.

### 2.3 Exigences de référencement

- **Contrat conforme au règlement 2025/1466.** Il décrit les rôles, l'échange des données de sécurité et les modalités d'audit et d'inspection. Toute sous-traitance ultérieure exige l'accord écrit du titulaire [S7, vérifié] : l'hébergeur et les fournisseurs de modèles doivent figurer au contrat.
- **Audit fournisseur de 1 à 3 jours.** Il porte sur les SOP, les CV, le plan de continuité et la disponibilité du QPPV 24 h sur 24 [hypothèse].
- **Validation et hébergement.** Dossier GAMP 5 et Annexe 11 (21 CFR Part 11 pour les clients américains), données dans l'EEE chez un hébergeur HDS, ISO 27001 souvent demandée [hypothèse].
- **Mise en concurrence.** Pas de marché public, mais un appel d'offres privé fréquent au-delà de 50 salariés [hypothèse].

### 2.4 Objections typiques

| Objection | Réponse et preuve |
|---|---|
| « Un agent va rater un cas grave » | Revue humaine de 100 % des cas graves, rapprochement mensuel avec les partenaires, SLA ; tableau de bord et audit blanc |
| « Combien de clients par QPPV ? » | Charge maximale publiée dans le PSMF, suppléants nommés |
| « Et si votre start-up disparaît ? » | Export E2B complet, séquestre des données, transition de 6 mois |
| « Nos données partent aux États-Unis » | Inférence en région UE sans conservation, narrations pseudonymisées, liste des sous-traitants |
| « La migration est trop risquée » | Migration prise en charge, rapprochement de 100 % des cas, période en parallèle |

## 3. Disposition à payer et modèles de prix

### 3.1 Points de référence

| Référence | Prix | Source | Confiance |
|---|---|---|---|
| QPPV interne, coût chargé | environ 148 k€ par an | S4 multiplié par 1,45 | estimé |
| PV interne minimale (QPPV, suppléant partiel, chargé de PV, base de sécurité, veille, audits) | 250 à 340 k€ par an | somme des postes, base à 20-60 k€ [hypothèse] | estimé |
| Tepsivo OnePV, petite structure (1 à 10 marchés) | 60 à 100 k€ par an | S3 | vérifié |
| Tepsivo OnePV, plus de 20 marchés | 200 à 350 k€ par an | S3 | vérifié |
| Contact local de PV par pays | 600 € par mois | S3 | vérifié |
| Veille bibliographique mondiale | 1 à 5 k€ par mois | S3 | vérifié |
| Licence de logiciel PV | 60 à 300 k€ par an | S3 | vérifié |
| Réception et soumission d'un cas par une CRO | 15 à 25 $ | S6 | hypothèse |
| Prix de marché implicite, petite structure | 200 à 330 k€ par an | 60-100 k€ divisés par 0,30 (S3) | estimé |

Une remise de 40 à 60 % est réaliste face aux CRO classiques, mais pas face aux prestataires outillés par l'IA, déjà au même niveau. Pour les petits titulaires français, les cabinets locaux facturent plutôt 30 à 80 k€ par an [hypothèse]. La différence doit venir d'un QPPV francophone qui cumule le rôle de responsable PV France, de l'expérience des inspections de l'ANSM, d'un SLA de conformité et de la transparence par substance.

### 3.2 Modèles de prix comparés

| Modèle | Utilisé par | Limite pour ce projet |
|---|---|---|
| Temps passé | CRO historiques | chaque gain apporté par l'IA réduit le chiffre d'affaires |
| Par cas | sous-traitants de traitement des cas | commoditisation ; volumes européens stables (1,76 M d'ICSR en 2024, soit -7,9 %, puis +0,5 % en 2025) [S11, S2, vérifié] |
| Abonnement au périmètre | Tepsivo, offres QPPV | à indexer sur le nombre de substances et de pays |
| Au résultat | rare | « zéro constat » invendable ; possible sous forme de SLA avec avoirs |
| Partage d'économies | rare | base de référence contestable ; réservé aux reprises de contrats CRO |

Retenu : l'abonnement au périmètre, complété d'un SLA. La stagnation des volumes contredit l'hypothèse d'une hausse de 10 % par an des ICSR : la part variable ne doit pas compter sur la croissance des volumes.

### 3.3 Grille recommandée [hypothèse]

| Offre | Périmètre | Prix mensuel | Au-delà du volume inclus |
|---|---|---|---|
| Essentiel | 5 substances, 100 cas par an, France ; QPPV EU et responsable PV France, PSMF, ICSR, veille, signaux, 1 PSUR | 2 000 € | 40 € par cas non grave, 150 € par cas grave |
| Standard | 15 substances, 400 cas par an, France et 2 pays, 2 PSUR, rapprochement avec les partenaires | 3 500 € | idem, et 500 € par mois et par pays supplémentaire |
| Lancement | 1 ou 2 substances nouvelles, plan de gestion des risques, PSUR semestriel, préparation d'inspection | 6 000 à 9 000 € | sur devis |
| Mise en place | migration validée, PSMF, notifications | 10 à 25 k€, une fois | |
| SLA | 100 % des cas graves à 15 jours, au moins 98 % des non graves à 90 jours | avoir de 10 % du forfait par mois hors cible | |

La grille démarre à 2 000 € et non à 1 500 € : en dessous, la marge brute d'un client Essentiel tombe sous 40 % (section 4).

## 4. Unit economics

### 4.1 Panier moyen

Avec 40 % de clients Essentiel (24 k€ par an), 45 % de Standard (42 k€) et 15 % de Lancement (84 k€), le revenu récurrent atteint 41 k€ par client. Avec environ 10 % de part variable, le panier annuel moyen (ARPA) atteint **45 k€**, plus 10 à 25 k€ de mise en place [estimé].

### 4.2 Coût de service d'un client Standard

Profil retenu : 300 cas par an dont 30 % graves, 10 substances hors MLM, 2 PSUR.

| Poste | Hypothèse | Coût annuel |
|---|---|---|
| Inférence | Environ 0,8 $ par cas : 150 000 jetons en entrée et 12 000 en sortie sur Sonnet 5.5 (2 $ et 10 $ par million), plus une relecture des cas graves sur Opus 5.5 (4 $ et 20 $) [S12]. S'y ajoutent la veille, les signaux et les PSUR ; le total est doublé pour les reprises et les tests. | environ 1 k€ [estimé] |
| Heures humaines | Environ 200 h à 65 € de l'heure (mélange d'un scientifique PV à 45 € et d'un QPPV à 92 €) : cas graves, contrôles, veille, signaux, PSUR, audits | environ 13 k€ [estimé] |
| Base validée, hébergement HDS, MedDRA, accès Embase | partagés entre 20 clients | 5 à 7 k€ [hypothèse] |
| Qualité, revalidation, assurance | quote-part | 2 à 3 k€ [hypothèse] |
| **Total** | | **21 à 24 k€** |

La marge brute atteint 45 à 50 % au lancement et vise 65 à 70 % à 100 clients, avec 120 heures humaines par client et des coûts partagés divisés par deux [estimé]. L'inférence pèse moins de 3 % du chiffre d'affaires : un modèle dix fois moins cher ne change presque rien. Le gain vient de la baisse des heures humaines. Un meilleur modèle augmente donc bien la marge, à condition que chaque revalidation reste peu coûteuse.

### 4.3 Acquisition et rétention

| Indicateur | Valeur | Méthode | Confiance |
|---|---|---|---|
| CAC | 25 à 30 k€ | un commercial (110 k€ chargés) et 40 k€ d'événements pour 6 signatures par an, plus le temps des audits de prospects | estimé |
| Récupération du CAC | 12 à 16 mois | CAC divisé par (ARPA × marge brute) | estimé |
| Clients perdus par an | 5 à 8 % | contrats de 3 à 5 ans ; départs surtout par rachat du client | hypothèse |
| Rétention nette du revenu | 105 à 115 % | ajout de produits et de pays | hypothèse |
| Valeur vie client sur 7 ans | environ 170 k€ | 45 k€ × 55 % de marge × 7 | estimé |
| LTV/CAC | environ 6 | | estimé |

Pour changer de prestataire, un client doit migrer sa base de façon validée, réécrire le PSMF, déclarer le nouveau QPPV dans la base de l'article 57 et auditer le nouveau fournisseur. Les départs viennent surtout de la consolidation des PME (la PV rachetée est intégrée chez l'acquéreur) ou d'un constat critique. Contrainte de capacité : un QPPV et son suppléant couvrent environ 20 à 25 clients [hypothèse], donc 4 à 5 QPPV pour 100 clients.

## 5. Go-to-market

### 5.1 Canaux

| Canal | Rôle | Priorité |
|---|---|---|
| Vente directe par le réseau du QPPV cofondateur | Seul canal crédible au départ : le client achète la confiance dans une personne | 1 |
| Fédérations : AMLIS, NèreS, GEMME, France Biotech, AFAR | Interventions et accès ciblé au vivier | 1 |
| Cabinets d'affaires réglementaires sans offre PV | Recommandation lors des nouvelles AMM, commission de 10 % la première année [hypothèse] | 2 |
| Exploitants pour compte de tiers (par exemple Movianto [S13]) | Apport de titulaires étrangers | 2 |
| Conseils en fusions-acquisitions, avocats en santé | Détection des rachats de portefeuille | 2 |
| Alliance avec un distributeur | Précédent : Clinigen entre au capital de Tepsivo en janvier 2025 [S14, vérifié] | 3 |
| Places de marché, intégrateurs | Peu pertinents pour une prestation nominative | 4 |

### 5.2 Les 10 premiers clients

| Période | Actions | Preuve produite |
|---|---|---|
| Mois 0 à 6 | Acheter une base de sécurité validée plutôt que la construire, rédiger environ 40 SOP, héberger chez un prestataire HDS, souscrire une RC professionnelle, faire réaliser un audit blanc par un ancien inspecteur | Rapport d'audit indépendant |
| Mois 4 à 9 | 2 pilotes : traiter en double, pendant 60 à 90 jours, les cas non graves et la veille d'un client, gratuitement ou à moitié prix | Accord du codage MedDRA, délais, temps humain par cas |
| Mois 9 à 12 | Premier contrat de 3 ans, avec un laboratoire OTC ou un génériqueur dont le QPPV part | Contrat signé |
| Mois 12 à 24 | Cibler 300 comptes ; suivre les décisions d'AMM, les transferts d'AMM et les offres d'emploi de QPPV ; offrir la mise en place aux 5 premiers en échange du droit de les citer | 10 clients, environ 0,45 M€ de revenu récurrent annuel [estimé] |

### 5.3 De 10 à 100 clients (années 3 à 6)

- **Géographie.** Belgique et Luxembourg d'abord, puis Espagne, Italie et Allemagne avec des QPPV locaux. À 100 clients : environ 4,5 M€ de revenu récurrent, 4 à 5 QPPV, 25 à 30 salariés [estimé].
- **Croissance externe.** Racheter un ou deux cabinets français de PV apporte des clients, des QPPV et un historique d'inspections, la preuve la plus difficile à produire seul [hypothèse].
- **Marketing.** Prix publics, tableau de bord ouvert aux clients, baromètre annuel de conformité fondé sur les données d'EudraVigilance.

### 5.4 Preuves à apporter

1. Un audit blanc indépendant dès le sixième mois.
2. Des taux de conformité supérieurs à la moyenne des titulaires (96,9 % à 15 jours, 80,4 % à 90 jours) [S2].
3. Un dossier de validation des agents aligné sur le document de réflexion de l'EMA sur l'IA (2024) et sur les travaux du CIOMS XIV.
4. Deux études de cas chiffrées.
5. Une première inspection de l'ANSM sans constat critique, imprévisible et attendue sous 1 à 3 ans [hypothèse].

## 6. Contraintes réglementaires à la vente

| Cadre | Ce qui s'applique | Effet sur la vente |
|---|---|---|
| Directive 2001/83/CE (article 104), règlement 520/2012 modifié par 2025/1466 | QPPV résidant dans l'UE ; contrat de sous-traitance encadré ; audits fondés sur les risques couvrant les sous-traitants ; exploitation obligatoire des données d'EudraVigilance. Applicable depuis le 12 février 2026 [S7, vérifié]. | Modèle de contrat et dossier d'audit prêts avant le premier rendez-vous |
| AI Act | Cas d'usage hors Annexe III, logiciel sans finalité médicale donc hors Annexe I : pas de haut risque [hypothèse]. Maîtrise de l'IA (article 4) depuis le 2 février 2025 ; obligations des éditeurs de modèles depuis le 2 août 2025. L'Omnibus IA (en vigueur le 27 juillet 2026) reporte l'Annexe III au 2 décembre 2027 et l'Annexe I au 2 août 2028 [S15, vérifié]. | Charge faible. Un agent de réception conversationnel doit annoncer qu'il est une IA [hypothèse]. |
| Doctrine EMA et CIOMS | Document de réflexion sur l'IA (2024), CIOMS XIV : approche par les risques, supervision humaine | Dossier de validation des agents à remettre en audit |
| Validation informatisée | GAMP 5, Annexe 11, Part 11 ; un projet d'Annexe 22 sur l'IA (consultation 2025) écarterait les modèles génératifs des usages critiques en BPF [hypothèse] | Chaque changement de modèle exige une revalidation ; risque si les inspecteurs GVP transposent cette logique |
| RGPD | Titulaire responsable du traitement, prestataire sous-traitant (article 28), éditeurs de modèles et hébergeur sous-traitants ultérieurs autorisés par écrit ; données de santé (article 9), analyse d'impact | Inférence dans l'UE sans conservation, pseudonymisation avant l'appel au modèle |
| HDS | Article L.1111-8 du Code de la santé publique ; référentiel v2 (arrêté du 26 avril 2024) : stockage dans l'EEE, certificat de 3 ans [S16, hypothèse]. Application à la PV discutée. | Héberger chez un prestataire certifié HDS quelle que soit l'interprétation |
| SecNumCloud | Non exigé pour des clients privés [hypothèse] | Argument face à un DPO sensible au Cloud Act |
| Secret professionnel | Pharmaciens et médecins tenus au secret ; clauses de confidentialité pour les autres salariés | Engagements inscrits au contrat |
| Responsabilité | Le titulaire reste responsable même s'il délègue [S9, vérifié] ; sanctions de l'ANSM (article L.5471-1) proportionnées au chiffre d'affaires du produit [S10, vérifié] | Responsabilité plafonnée à 1 ou 2 ans d'honoraires, RC professionnelle de 2 à 5 M€, amendes exclues sauf faute lourde [hypothèse] |

## Sources

- **[S1]** AMLIS, *Panorama 2024 des PME et ETI du médicament en France*, publié le 24/09/2024, https://www.amlis.fr/wp-content/uploads/2024/10/Panorama-PME-Sante-2024.pdf (consulté le 2026-11-03)
- **[S2]** EMA, *2025 Annual Report on EudraVigilance* (EMA/371010/2025), 12/03/2026, https://www.ema.europa.eu/en/documents/report/2025-annual-report-eudravigilance-european-parliament-council-commission_en.pdf (consulté le 2026-11-03)
- **[S3]** Tepsivo, page *Pricing*, https://www.tepsivo.com/pricing/ (consulté le 2026-11-03)
- **[S4]** Michael Page, grille de salaires « Responsable pharmacovigilance » (édition 2027), https://www.michaelpage.fr/grilles-de-salaires/life-sciences/affaires-pharmaceutiques-responsable-pharmacovigilance (consulté le 2026-11-03)
- **[S5]** France Travail, offres consultées le 2026-11-03 :
  - EU-QPPV et pharmacovigilant senior, Paris : https://candidat.francetravail.fr/offres/recherche/detail/4647911
  - QPPV et responsable PV, Lyon : https://candidat.francetravail.fr/offres/recherche/detail/191PYCC
  - Responsable PV EU-QPPV, Paris : https://candidat.francetravail.fr/offres/recherche/detail/4461139
- **[S6]** IntuitionLabs, *AI ROI in Pharmacovigilance: Building the Business Case*, mis à jour le 16/10/2026, https://intuitionlabs.ai/articles/ai-roi-pharmacovigilance-business-case (consulté le 2026-11-03)
- **[S7]** Sources sur le règlement d'exécution (UE) 2025/1466 :
  - Sidley Austin, octobre 2025, https://www.sidley.com/en/insights/newsupdates/2025/10/adapting-to-change-key-compliance-risks-under-the-revised-eu-pharmacovigilance-rules
  - The Entourage, 08/08/2026, https://theentourage.us/en/insights/qppv-outsourcing-2025-1466-vertrag-audit
- **[S8]** EMA, *Medical literature monitoring*, https://www.ema.europa.eu/en/human-regulatory-overview/post-authorisation/pharmacovigilance-post-authorisation/medical-literature-monitoring (consulté le 2026-11-03)
- **[S9]** Swim Legal, *Pharmacovigilance : obligations et responsabilités des laboratoires*, 06/06/2026, https://www.swim.legal/blog/pharmacovigilance-obligations-responsabilites-laboratoires (consulté le 2026-11-03)
- **[S10]** ANSM :
  - *Rapport d'activité 2025*, https://ansm.sante.fr/qui-sommes-nous/rapport-dactivite-2025/rapport-dactivite-2025/p/edito-3
  - Lignes directrices sur les sanctions financières, 08/08/2022, https://ansm.sante.fr/actualites/ruptures-de-stock-de-medicaments-lansm-actualise-ses-lignes-directrices-relatives-aux-sanctions-financieres (consultées le 2026-11-03)
- **[S11]** EMA, *2024 Annual Report on EudraVigilance* (EMA/559856/2024), 20/03/2025, https://www.ema.europa.eu/en/documents/report/2024-annual-report-eudravigilance-european-parliament-council-commission_en.pdf
- **[S12]** Anthropic, *Pricing*, https://platform.claude.com/docs/en/about-claude/pricing (consulté le 2026-11-03)
- **[S13]** Movianto, *Exploitation d'AMM*, https://movianto.com/fr/services/services-a-valeur-ajoutee/exploitation-damm-centre-specialites-pharmaceutiques/ (consulté le 2026-11-03)
- **[S14]** Partenariat Clinigen et Tepsivo, janvier 2025 :
  - Samedan, https://www.samedanltd.com/press-releases/clinigen-announces-strategic-partnership-with-tepsivo/
  - PharmaNow, https://www.pharmanow.live/latest-news/clinigen-partners-with-tepsivo-for-pv-efficiency
- **[S15]** Commission européenne, *Regulatory framework on AI*, https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai (consulté le 2026-11-03)
- **[S16]** Sources sur la certification HDS :
  - Wikipédia, *Hébergeur de données de santé*, https://fr.wikipedia.org/wiki/H%C3%A9bergeur_de_donn%C3%A9es_de_sant%C3%A9 (consulté le 2026-11-03)
  - Agence du numérique en santé, https://esante.gouv.fr/produits-services/hds
