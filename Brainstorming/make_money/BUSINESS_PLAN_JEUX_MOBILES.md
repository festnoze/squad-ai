# Business plan — jeux mobiles assistés par IA, publicité et achats intégrés

Analyse au 6 septembre 2026. Montants en euros sauf mention USD. Perspective : créateur solo, jeu casual de petite taille, outils IA utilisés pour produire le jeu et ses contenus. Modèle financier : 12 mois de 30 jours depuis le début du projet, sans historique réel.

## 1. Conclusion d’investissement

**Le modèle peut rapporter de l’argent, mais produire vite des jeux ne suffit pas à créer une activité rentable.** Pour un solo, l’intérêt financier réside dans un jeu qui conserve suffisamment ses joueurs, peut attirer des installations à faible coût et demande peu de contenu supplémentaire. Le principal risque est d’obtenir un produit techniquement terminé dont chaque nouveau joueur coûte davantage qu’il ne rapporte.

Je recommande un **petit jeu casual hybride**, avec vidéos récompensées facultatives, interstitiels limités, achat de retrait des publicités imposées et quelques objets clairement définis. Financer un prototype et un test de marché, puis décider. Ne pas lancer une usine à jeux avant d’avoir validé la distribution d’un premier titre.

Le modèle associé compare trois situations, sans leur attribuer de probabilité :

| Indicateur, année 1 | Prudent | Central | Favorable exigeant |
|---|---:|---:|---:|
| Installations cumulées | 2 350 | 20 511 | 136 250 |
| Dont installations payées | 500 | 1 111 | 69 250 |
| Dépenses d’acquisition | 600 € | 1 000 € | 27 700 € |
| Revenus publicitaires éditeur | 28 € | 1 172 € | 35 015 € |
| Achats intégrés nets éditeur | 32 € | 817 € | 24 059 € |
| Revenus éditeur totaux | **60 €** | **1 989 €** | **59 074 €** |
| Résultat après dépenses cash, création comprise | **−4 547 €** | **−3 693 €** | **+22 567 €** |
| Temps du créateur | 385 h | 475 h | 610 h |
| Résultat après valorisation du temps à 30 €/h | **−16 097 €** | **−17 943 €** | **+4 267 €** |
| Besoin maximal de trésorerie avant réserve | 4 552 € | 4 217 € | 6 070 € |
| Résultat cash du mois 12 | −195 € | +141 € | +7 302 € |

Ces résultats sont des **calculs conditionnels, pas une prévision de gains**. Le scénario central n’est pas une médiane statistique. Le favorable combine volontairement plusieurs bonnes performances simultanées ; il ne doit pas servir de budget de base. Il suppose aussi presque 67 000 installations organiques sur l’année, qui restent entièrement à conquérir.

Le modèle maintient le scénario prudent jusqu’à douze mois pour montrer le coût de persister. Le plan opérationnel recommande au contraire d’arrêter beaucoup plus tôt un titre dont les tests échouent.

## 2. Périmètre et définitions financières

Cette étude prolonge les recherches de `make_money`. Elle analyse l’opportunité économique ; elle ne lance aucune campagne et ne construit pas de jeu.

**Hypothèse de travail.** Un jeu solo jouable sans serveur permanent, Android en premier pour concentrer les tests, puis iOS si les résultats et les moyens le justifient. Marché visé : joueurs casual adultes, francophones et anglophones. Le choix d’Android est une proposition de séquencement, pas une affirmation qu’il rapporte toujours davantage qu’iOS.

Le modèle réserve 250 heures à la création et au lancement sur M1–M3, dont 100 heures pendant chacun des deux premiers mois. Cela demande environ 23 heures par semaine au début. **Avec seulement 10–15 heures par semaine, prévoir plutôt 17–25 semaines pour ces 250 heures**, et décaler les recettes de lancement. Il faut modifier le calendrier avant de l’utiliser comme budget personnel.

| Terme | Définition utilisée |
|---|---|
| Installation | Premier lancement d’un nouveau joueur, cohorte d’acquisition ; distinguer des réinstallations |
| DAU | Joueurs actifs un jour donné ; ici moyenne quotidienne du mois |
| Rétention D7 | Part de la cohorte active exactement sept jours après installation, pas au moins une fois dans la semaine |
| Jour actif | Un joueur actif pendant une journée, quel que soit son nombre de sessions |
| eCPM | Revenu pour mille impressions publicitaires effectivement servies |
| IAP | Achats intégrés, ici retrait de pubs, skins et powerups |
| LTV à 180 jours | Revenu net éditeur cumulé attendu par installation sur D0–D179 |
| Contribution à 180 jours | LTV moins coût variable de service du joueur, avant acquisition et frais fixes |
| CPI | Dépense d’acquisition divisée par installations attribuées à cette dépense |
| Résultat cash gagné | Revenus acquis moins dépenses cash ; indépendamment de la date du versement |
| Trésorerie | Encaissements réellement décalés moins décaissements ; un solde négatif indique le financement nécessaire |
| Résultat économique | Résultat cash gagné moins valeur du temps travaillé ; pas une déclaration fiscale |

Le revenu éditeur publicitaire est supposé déjà net de la rémunération des intermédiaires représentée dans l’eCPM. On ne retire pas une seconde fois une commission boutique sur ces revenus publicitaires. Pour les IAP, on retire une TVA moyenne illustrative, les frais boutique et les remboursements. Le traitement comptable légal du chiffre d’affaires peut différer selon les contrats : « revenus éditeur » sert ici à comparer les sommes économiquement disponibles.

## 3. Marché, concurrence et positionnement

Le marché existe, mais il n’est pas nécessaire d’invoquer ses milliards pour justifier un petit studio. La question utile est : **peut-on acquérir quelques milliers de joueurs bien ciblés qui reviennent et génèrent une contribution positive ?** Le modèle estime ce nombre par le bas.

Trois repères externes structurent l’analyse :

- GameAnalytics décrit, dans son rapport 2026 portant sur 2025, une rétention D1 médiane autour de 22 %, un D7 médian inférieur à 4 % et un D30 médian autour de 0,68–0,79 %. Les meilleurs déciles font sensiblement mieux. Ce sont des jeux présents dans son échantillon, pas la probabilité de succès d’un nouveau jeu. [GameAnalytics 2026](https://www.gameanalytics.com/reports/2026-mobile-pc-gaming-benchmarks).
- Le rapport Appodeal intitulé « 2025 » consulté couvre octobre–décembre **2024**. Il distingue vidéos récompensées, interstitiels, bannières, plateformes et régions. Il justifie de segmenter l’analyse ; il ne fournit pas un tarif garanti en 2026. [Rapport Appodeal](https://appodeal.com/wp-content/uploads/2025/03/Appodeal-The-Latest-eCPM-Report-2025.pdf).
- AppsFlyer présente en janvier 2026 un contexte où la multiplication des créations et des lancements assistés par IA accroît la concurrence marketing. L’IA réduit une partie du coût de fabrication, mais ne crée pas automatiquement l’attention du joueur. [AppsFlyer, State of Gaming 2026](https://www.appsflyer.com/company/newsroom/pr/gaming-marketing/).

Les prix publicitaires et CPI du tableur sont **des hypothèses EUR à tester**, pas une conversion silencieuse de benchmarks USD. Ne pas assembler un CPI mesuré dans un pays peu cher avec un eCPM américain et une conversion IAP iOS. Chaque décision d’acquisition doit porter sur le même pays, OS, canal et type de joueur.

### Produit conseillé

Un jeu de puzzle ou d’adresse léger, compréhensible en quelques secondes, avec sessions courtes, progression visible, défi quotidien et collection cosmétique. Exemple de direction à tester : puzzles de rangement/assemblage avec solutions variées et thèmes visuels à collectionner. L’idée précise doit être validée par des joueurs ; le modèle financier ne prouve pas son attractivité.

Promesse au joueur : quelques minutes de jeu satisfaisantes, progression sans paiement obligatoire, contenus visuels soignés et achats sans ambiguïté. L’accroche visuelle doit être démontrable dans une vidéo fidèle de 10–20 secondes.

### Comparaison de familles de jeux

Estimations de complexité pour un solo, pas budgets industriels :

| Famille | Revenus naturels | Intérêt financier | Difficulté déterminante |
|---|---|---|---|
| Petit puzzle casual avec progression | Hybride, indices, retrait pubs, thèmes | Bon candidat au test | Trouver une mécanique différenciée et maintenir des niveaux intéressants |
| Arcade / runner à parties courtes | Publicité, seconde chance, skins | Production accessible, panier faible | Rétention et coût d’acquisition |
| Idle / incremental léger | Récompenses vidéo, boosts, progression | Potentiel de fréquence et achats répétés | Équilibrage économique, sauvegarde et rythme de progression |
| Collection / décoration plus profonde | Skins, packs, événements | Potentiel IAP supérieur | Volume d’assets et animation récurrente |
| Jeu compétitif multijoueur | Cosmétiques, pass | Non prioritaire pour le premier titre | Serveurs, triche, matchmaking, communauté et support |
| Jeu destiné aux enfants | Modèle spécifique à définir | À exclure du premier business case | Contraintes de données, publicité et achats à traiter séparément |

L’absence de multijoueur diminue les coûts mais affaiblit parfois l’intérêt des skins : sans visibilité sociale, leur valeur dépend davantage de l’attachement au personnage, de la collection et de la personnalisation.

## 4. Comparaison publicité, IAP et hybride

| Modèle | Ce qui rapporte | Avantages | Limites | Verdict pour le premier jeu |
|---|---|---|---|---|
| Publicité seule | Impressions servies | Monétise aussi les non-payeurs | Très dépendant du volume, du pays et de la rétention | Viable seulement si acquisition très peu chère ou distribution organique efficace |
| IAP seuls | Skins, packs, powerups | Pas de publicité imposée ; panier extensible | La majorité des joueurs peut ne jamais payer | À tester si le jeu crée un fort désir d’achat et de rétention |
| Hybride | Pub + achats, avec cannibalisation | Plusieurs sources ; le retrait pubs répond à une préférence réelle | Plus de complexité et arbitrages entre plaisir, revenu et progression | Choix initial recommandé, modéré et mesuré |

Le revenu hybride n’est pas simplement « toute la pub + tous les achats ». L’achat de retrait de pubs supprime des impressions ; les vidéos récompensées peuvent remplacer certains achats de boosts ; une pression commerciale excessive peut diminuer les jours de jeu.

Dans le modèle, à **rétention et achats de skins/powerups identiques** :

| Revenus nets par installation sur 180 jours | Prudent | Central | Favorable |
|---|---:|---:|---:|
| Pub seule, aucun retrait pubs | 0,012 € | 0,067 € | 0,350 € |
| IAP seuls, retrait pubs exclu | 0,004 € | 0,019 € | 0,137 € |
| Hybride, retrait pubs inclus et pub réduite | **0,027 €** | **0,112 €** | **0,543 €** |

C’est une comparaison mécanique, pas une démonstration que l’hybride gagne dans tout jeu. Un design sans pub pourrait améliorer suffisamment la rétention ou les achats pour changer le classement. Un jeu IAP profond ne se modélise pas avec les taux d’un petit puzzle.

### Catalogue d’achats proposé

Tarifs indicatifs TTC, à adapter aux paliers, devises et tests locaux :

| Produit | Prix test | Règle produit | Fonction économique |
|---|---:|---|---|
| Retrait des publicités imposées | 4,99 € unique | Retire interstitiels et bannières ; vidéos facultatives décrites explicitement | Conversion de joueurs préférant payer pour le confort |
| Skin / thème | 2,99 € en moyenne | Prévisualisation et contenu déterminé | Achat émotionnel sans bloquer le gameplay |
| Pack de powerups | 1,99 € en moyenne | Quantité connue, usage non obligatoire | Achats possibles à plusieurs reprises |
| Pack de lancement combiné | À tester après les produits individuels | Contenu et valeur transparents | Non ajouté au modèle pour éviter un double comptage |
| Pass / abonnement | Différé | Seulement avec un vrai programme de contenu récurrent | Engagement d’exploitation trop lourd au lancement |

Un achat de retrait de pubs est un non-consommable : il faut restaurer le droit après réinstallation. Les powerups consommables demandent un historique fiable des attributions. L’intégration doit éviter de débiter sans livrer ou de livrer deux fois après une reprise réseau. Ces coûts de fiabilité sont inclus dans le travail de lancement ; ils ne disparaissent pas avec la génération de code par IA.

### Placement publicitaire initial

- Vidéo récompensée seulement à l’initiative du joueur : indice, seconde chance ou récompense explicitement annoncée.
- Interstitiels à une transition naturelle, jamais pendant une action. Tester par exemple un premier déclenchement après plusieurs parties et un plafond temporel, plutôt qu’un écran à chaque échec.
- Pas de bannière dans le premier modèle. Son revenu potentiel peut être ajouté plus tard si un test montre un effet global positif.
- Un achat « sans publicités » doit préciser exactement ce qu’il retire. Si des vidéos facultatives restent proposées, l’indiquer avant l’achat.

Les nombres d’impressions du modèle sont des **moyennes sur tous les jours actifs**, pas des plafonds recommandés ni le nombre de vidéos regardées par chaque joueur.

## 5. Hypothèses du modèle par cohorte

La rétention au jour exact est interpolée linéairement entre les points ci-dessous. À chaque date, on additionne les joueurs encore actifs issus de toutes les cohortes d’installation. On ne multiplie donc pas un taux D30 par tout le parc pour inventer des DAU.

| Paramètre | Prudent | Central | Favorable exigeant |
|---|---:|---:|---:|
| D1 | 22 % | 32 % | 42 % |
| D7 | 4 % | 8 % | 16 % |
| D30 | 0,8 % | 2 % | 6 % |
| D90 | 0,2 % | 0,6 % | 2,5 % |
| D180 | 0,08 % | 0,2 % | 1,2 % |
| D359 | 0,01 % | 0,05 % | 0,5 % |
| Jours actifs cumulés par installation sur 180 jours | 2,87 | 4,65 | 9,69 |
| eCPM récompensé net éditeur | 5 € | 10 € | 16 € |
| eCPM interstitiel net éditeur | 2 € | 4 € | 7 € |
| Demandes récompensées par jour actif | 0,6 | 1,0 | 1,5 |
| Demandes interstitielles par jour actif avant retrait | 1,2 | 1,5 | 2,0 |
| Demande → impression effectivement servie | 80 % | 90 % | 95 % |
| Part des jours actifs dispensés d’interstitiels | 1,5 % | 4 % | 10 % |
| Acheteurs retrait pubs / installations à 90 jours | 0,3 % | 0,8 % | 2 % |
| Acheteurs skins / installations à 90 jours | 0,1 % | 0,3 % | 1,2 % |
| Acheteurs powerups / installations à 90 jours | 0,1 % | 0,4 % | 1,8 % |
| Achats skins par acheteur à 90 jours | 1 | 1,2 | 1,5 |
| Achats powerups par acheteur à 90 jours | 1,5 | 2 | 4 |
| CPI payé | 1,20 € | 0,90 € | 0,40 € |

Les catégories d’acheteurs peuvent se recouper : on additionne leurs dépenses attendues, **pas leurs taux pour obtenir des payeurs uniques**. Le nombre de jours actifs sans pubs peut dépasser le taux d’achat, car les acheteurs peuvent jouer plus longtemps ; c’est ici un paramètre indépendant, à mesurer ensuite par segment. Ce proxy ne décrit pas exactement la date individuelle du retrait de pubs.

L’hypothèse favorable de CPI 0,40 € avec eCPM et rétention élevés est particulièrement exigeante. Elle représente une combinaison à démontrer dans une même cohorte, pas un tarif disponible sur commande.

### Formules essentielles

```text
Pub par jour actif = taux de livraison ×
  [demandes récompensées × eCPM récompensé
   + demandes interstitielles × (1 − part jours sans pubs) × eCPM interstitiel]
  / 1 000

IAP TTC par installation =
  taux acheteurs retrait × prix retrait
  + taux acheteurs skins × achats par acheteur × prix skin
  + taux acheteurs boosts × achats par acheteur × prix pack

IAP nets = IAP TTC / (1 + TVA moyenne)
           × (1 − commission boutique) × (1 − remboursements)

LTV180 = somme des jours actifs D0–D179 × pub par jour actif + IAP nets à 90 jours

Contribution180 = LTV180 − coût variable par jour actif × jours actifs D0–D179

CPI maximal prudent = Contribution180 / 1,30
```

Hypothèses communes : TVA moyenne illustrative 20 %, commission 15 % sous conditions d’éligibilité, remboursements 2 %, coût variable 0,001 € par jour actif. Aucun de ces paramètres n’est une estimation personnalisée de la fiscalité de ton entreprise.

La recette IAP de cohorte est étalée : 40 % pendant D0–D6, 35 % pendant D7–D29, 25 % pendant D30–D89. Aucun IAP supplémentaire après D89 n’est ajouté. Cela simplifie fortement les comportements des acheteurs réguliers ; le modèle devra utiliser les achats réellement observés dès qu’ils existent.

## 6. Ce que peut rapporter la publicité

Avec la politique hybride du modèle :

| DAU moyens | Pub/mois prudent | Pub/mois central | Pub/mois favorable |
|---:|---:|---:|---:|
| 100 | 13 € | 43 € | 104 € |
| 1 000 | 129 € | 426 € | 1 043 € |
| 10 000 | 1 287 € | 4 255 € | 10 431 € |

Un jeu avec 10 000 téléchargements cumulés peut donc rapporter très peu s’il n’a plus que quelques dizaines de joueurs quotidiens. Les DAU sont un stock entretenu par la rétention et l’arrivée de nouveaux joueurs ; les téléchargements cumulés ne sont pas un revenu récurrent.

Dans le scénario central, un joueur rapporte environ **0,0142 € par journée active en publicité**. Une impression supplémentaire ne change pas forcément la rentabilité si elle fait perdre plusieurs journées futures de jeu. Le bon critère d’un test publicitaire est la contribution de cohorte, pas l’eCPM isolé.

### Le retrait des pubs est-il rentable ?

À 4,99 € TTC, avec les paramètres du modèle : 4,99 / 1,20 × 0,85 × 0,98 = **3,46 € nets**. Un acheteur central qui aurait joué 30 journées supplémentaires abandonnerait environ 30 × 1,5 × 90 % × 4 / 1 000 = **0,162 €** de revenus interstitiels.

Sur cet exemple, le gain direct est d’environ **3,30 €** avant effets de rétention et autres achats. La vente paraît intéressante, mais cela ne signifie pas que beaucoup de joueurs achèteront. Il faut aussi examiner les gros consommateurs de pubs et ne pas assimiler le joueur payeur au joueur moyen.

Pour éviter le double comptage, les revenus IAP de retrait sont déjà inclus dans la LTV hybride, et les revenus interstitiels y sont déjà réduits.

## 7. Peut-on acheter des joueurs avec bénéfice ?

| Indicateur | Prudent | Central | Favorable |
|---|---:|---:|---:|
| LTV nette à 180 jours | 0,027 € | 0,112 € | 0,543 € |
| Contribution à 180 jours | 0,024 € | 0,108 € | 0,533 € |
| CPI payé supposé | 1,20 € | 0,90 € | 0,40 € |
| Contribution / CPI | 0,02× | 0,12× | 1,33× |
| CPI maximal avec marge de sécurité 30 % | 0,018 € | 0,083 € | 0,410 € |
| Retour du coût d’acquisition, revenus gagnés | Non atteint à 180 j | Non atteint à 180 j | Environ 54 j |

Dans le scénario central, dépenser 900 € pour 1 000 installations donne environ 108 € de contribution à six mois : **792 € perdus avant même les coûts fixes et les créations publicitaires**. Augmenter les dépenses amplifie le problème.

Dans le favorable, le retour vers le 54e jour ne signifie pas argent reçu en banque ce jour-là. Le modèle ajoute un mois de décalage de paiement. La marge reste mince : un CPI de 0,65 € rendrait la contribution à 180 jours négative de près de 0,117 € par installation. À 0,90 €, la perte serait d’environ 0,367 €.

**Une bonne rentabilité globale grâce à l’organique ne justifie pas une campagne déficitaire.** Calculer LTV et CPI par canal. Le tableur suppose, faute de données, les mêmes rétentions et achats pour payé et organique ; cette simplification doit être supprimée dans les données de test.

La croissance des dépenses du favorable après les tests est une trajectoire conditionnelle. Les cellules ne déclenchent aucun arrêt automatique. Si les cohortes payées n’atteignent pas les seuils, mettre les budgets futurs à zéro plutôt que conserver le scénario par optimisme.

## 8. Acquisition et distribution

### Organique : un canal de travail, pas une ressource gratuite

Le scénario central suppose une progression de 300 installations organiques au lancement à 4 000 par mois en M12. Le favorable passe de 500 à 15 000. Il faut une stratégie capable de produire ces chiffres : vidéos montrant le gameplay, page boutique convaincante, référencement de niche, mises à jour et recommandations des joueurs.

Plan de départ :

1. Choisir une promesse de jeu et produire 3–5 vidéos fidèles avec des accroches différentes.
2. Tester intérêt et compréhension auprès de joueurs externes, sans compter les proches comme preuve de demande.
3. Travailler icône, captures et première vidéo boutique ; mesurer visite → installation avec les outils disponibles.
4. Publier régulièrement des démonstrations courtes et réutiliser les formats qui apportent des joueurs retenus.
5. Contacter quelques petits créateurs pertinents avec un accès au jeu ; toute prestation payante entre dans le budget marketing.

Illustration de l’effort : à un taux hypothétique de 20 % de visite boutique → installation, 4 000 installations demandent 20 000 visites. À 1 % de clic depuis une vidéo, cela représenterait 2 millions de vues si ce canal était seul. Ces taux ne sont pas des benchmarks : ils montrent pourquoi une courbe organique ne peut pas être considérée comme acquise.

### Acquisition payée

Commencer avec un seul OS et quelques segments pays distincts. Mesurer impressions, clics, visites, installations, rétention et revenus de la même cohorte. Conserver des créations et pages correspondant au vrai jeu pour ne pas acheter des joueurs qui repartent immédiatement.

Au départ, une enveloppe de **500–1 000 €** sert à tester, pas à rendre le projet rentable. Répartir l’apprentissage sans fragmenter les groupes au point qu’aucune mesure ne soit interprétable. Les coûts de création vidéo sont distincts du budget média dans le tableur.

### Éditeur / publisher

Option à envisager après prototype convaincant : un éditeur peut apporter tests, campagnes, créations et exploitation. Les contrats et partages varient ; aucune fraction « standard » n’est retenue ici. Comparer au minimum qui finance les campagnes, dans quel ordre les dépenses sont récupérées, qui détient le jeu et les données, ce qui est exclusif et les conditions de sortie.

Une avance n’est pas nécessairement un bénéfice ; un partage de revenus avant ou après recouvrement des coûts donne des résultats très différents. Faire un modèle séparé à partir d’une proposition contractuelle réelle.

## 9. Budget de création et coûts récurrents

Budget cash initial modélisé, **hors ton travail et acquisition** :

| Poste | Provision |
|---|---:|
| Assets visuels et audio, licences et retouches | 650 € |
| Tests, appareils complémentaires ou prestation QA | 600 € |
| Localisation, captures et éléments boutique | 300 € |
| Revue confidentialité / accessibilité / marge de lancement | 250 € |
| **Total** | **1 800 €** |

Ce sont des enveloppes internes, pas des devis. Elles supposent déjà un PC adapté. Ajouter un Mac ou une prestation de build iOS si nécessaire, ainsi que tout appareil manquant. Si tu possèdes déjà les équipements ou assets, réduire la dépense cash correspondante sans supprimer le temps de validation.

Le modèle étale le développement cash en 900 € M1, 600 € M2 et 300 € M3. Le temps 100 + 100 + 50 heures vaut 7 500 € à 30 €/h. Un jeu terminé avec 1 800 € de sorties bancaires représente donc environ **9 300 € de ressources de lancement** avant marketing récurrent.

| Poste mensuel | Prudent | Central | Favorable |
|---|---:|---:|---:|
| Outils, comptes, hébergement et administration | 100 € | 150 € | 250 € |
| Créations marketing à partir de M3 | 100 € | 100 € | 300 € |
| Coût variable par jour actif | 0,001 € | 0,001 € | 0,001 € |
| Heures après lancement | 15 h | 25 h | 40 h |

Les frais fixes provisionnent aussi les abonnements et inscriptions aux plateformes ; ne pas les ajouter une seconde fois au total. Les outils gratuits n’éliminent pas les contrôles, corrections et mises à jour des SDK.

Repères vérifiés : programme développeur Apple à **99 USD/an**, inscription Google Play à **25 USD**. Unity Personal est proposé sous un seuil d’éligibilité de 200 000 USD de revenus/financement ; Unity a annulé sa Runtime Fee. Les services cloud et outils supplémentaires gardent leurs propres coûts. Aucun prix USD n’est automatiquement converti à parité en EUR dans les calculs. [Apple](https://developer.apple.com/programs/enroll/), [Google](https://support.google.com/googleplay/android-developer/answer/6112435), [Unity Personal](https://unity.com/products/unity-personal), [annulation Runtime Fee](https://unity.com/blog/unity-is-canceling-the-runtime-fee).

### Où l’IA économise réellement

Prototypage, génération de variantes graphiques, assistance aux scripts, localisation initiale, recherche de bugs et préparation de créations marketing. Les économies apparaissent dans moins d’heures ou moins de sous-traitance ; elles ne doivent pas être comptées une seconde fois comme revenu.

Le gameplay, la cohérence artistique, la stabilité sur téléphone, le plaisir, l’équilibrage des achats et l’efficacité publicitaire demandent toujours des tests humains. Le modèle **n’intègre aucun appel LLM pendant chaque partie**. Un jeu reposant sur de la génération en temps réel aurait un coût variable et un profil de risque différents.

## 10. Prévision mensuelle et besoin de financement

Extrait des deux scénarios principaux. « Résultat » inclut les dépenses cash de création mais pas la valeur du temps. « Trésorerie » suppose un versement des revenus du mois précédent et aucun apport initial.

| Mois | Revenus central | Résultat central | Trésorerie central | Revenus favorable | Résultat favorable | Trésorerie favorable |
|---:|---:|---:|---:|---:|---:|---:|
| M1 | 0 € | −1 050 € | −1 050 € | 0 € | −1 150 € | −1 150 € |
| M2 | 0 € | −750 € | −1 800 € | 0 € | −850 € | −2 000 € |
| M3 | 53 € | −999 € | −2 852 € | 534 € | −1 025 € | −3 559 € |
| M4 | 90 € | −663 € | −3 553 € | 1 166 € | −403 € | −4 594 € |
| M5 | 90 € | −164 € | −3 716 € | 2 045 € | −39 € | −5 511 € |
| M6 | 115 € | −140 € | −3 881 € | 3 213 € | +610 € | −6 070 € |
| M7 | 151 € | −105 € | −4 022 € | 4 533 € | +1 408 € | −5 983 € |
| M8 | 192 € | −66 € | −4 129 € | 6 065 € | +2 413 € | −5 102 € |
| M9 | 242 € | −18 € | −4 197 € | 7 726 € | +3 545 € | −3 218 € |
| M10 | 296 € | +34 € | −4 217 € | 9 462 € | +4 750 € | −204 € |
| M11 | 351 € | +87 € | −4 186 € | 11 252 € | +6 007 € | +4 014 € |
| M12 | 408 € | +141 € | −4 101 € | 13 079 € | +7 302 € | +9 488 € |

La première année du favorable génère 22 567 € de résultat cash gagné mais seulement 9 488 € de trésorerie cumulée avant apport, car **13 079 € restent à recevoir** en fin de M12. Le financement maximal intervient autour de M6. Prévoir une réserve de 25–30 % : environ **7 600–7 900 €**, arrondissable à 8 000 €, hors tes dépenses personnelles.

Le modèle utilise un mois de décalage pour toutes les sources. En pratique les contrats, seuils, vérifications et dates de paiement varient ; AdMob mentionne notamment des paiements autour du 21 du mois suivant sous conditions. Tester deux mois de décalage dans le classeur. À très faible revenu, les seuils peuvent retarder davantage l’encaissement. [AdMob paiements](https://support.google.com/admob/answer/2772140).

Les budgets média annuels ne doivent pas être confondus avec le capital initial : les revenus réinvestis financent une partie des campagnes du favorable. Réciproquement, un faible capital initial ne permet pas de dépenser librement tant que les versements n’arrivent pas.

## 11. Combien de joueurs pour gagner 3 000 € par mois ?

À maturité, avec des acquisitions organiques constantes et la LTV à 360 jours, le modèle donne :

| Objectif | Prudent | Central | Favorable |
|---|---:|---:|---:|
| 3 000 €/mois après coûts cash, avant prélèvements | ~132 000 installs/mois | ~29 400 installs/mois | ~6 100 installs/mois |
| Même surplus, après valorisation du travail récurrent | ~150 600 installs/mois | ~36 200 installs/mois | ~8 100 installs/mois |

Ces seuils supposent zéro acquisition payée, les coûts récurrents du scénario et un portefeuille de cohortes arrivé à maturité. Ils ne sont pas atteints immédiatement après un pic d’installations. La première ligne n’est pas 3 000 € nets personnels après cotisations et impôts ; sans statut fiscal, ce calcul serait trompeur.

Pour amortir seulement les 1 800 € de création cash avec la contribution à 180 jours, sans acquisition ni frais fixes, il faudrait environ **16 740 installations dans le central**, ou **3 375 dans le favorable**. Ce seuil partiel est utile, mais ne signifie pas activité rentable : le marketing, le temps et l’exploitation restent à financer.

## 12. Sensibilités et risques qui changent la décision

### Plus de monétisation ne suffit pas toujours

Dans le central, la LTV180 est de 0,112 €. Doubler les IAP à publicité et rétention constantes la porte à environ **0,158 €**. Doubler uniquement la publicité la porte à environ **0,178 €**. Cela reste très inférieur au CPI de 0,90 €. Le problème ne se résout pas seulement avec un bouton d’achat supplémentaire.

Passer la commission IAP de 15 % à 30 %, avec le même catalogue, diminue la recette nette IAP d’environ 17,6 %. L’effet sur le revenu total dépend de la part IAP. Les programmes réduits nécessitent de vérifier l’éligibilité et l’inscription, pas seulement d’être un petit studio. [Apple Small Business](https://developer.apple.com/app-store/small-business-program/), [Google frais de service](https://support.google.com/googleplay/android-developer/answer/112622).

### Registre des risques

| Risque | Effet financier | Réponse opérationnelle |
|---|---|---|
| Rétention faible | Faible LTV même avec beaucoup d’installations | Tester boucle de jeu avant la boutique et les événements |
| CPI qui augmente avec le budget | Marge des nouvelles cohortes qui disparaît | Augmentation progressive, contrôle du coût marginal |
| eCPM saisonnier ou géographie différente | Revenu publicitaire surestimé | Séparer OS/pays, stress test −25 à −50 % |
| Conversion IAP concentrée sur quelques joueurs | Moyenne très instable sur petit échantillon | Examiner médiane, concentration et intervalle de confiance |
| Achat non livré / non restauré | Remboursements, avis négatifs, support | Sandbox, validation, attribution idempotente et restauration |
| SDK publicitaire instable | Crashes et perte de joueurs | Tests appareils, monitoring et désactivation à distance |
| Contenu coûteux | Temps d’exploitation dépasse la marge | Boucle rejouable, production en lots, catalogue limité |
| Organique surestimé | Volumes et résultat favorable non atteints | Traiter chaque hausse comme hypothèse, suivre sa source |
| Jeu cloné ou assets litigieux | Retrait boutique ou coûts de reprise | Design distinct et droits documentés |
| Trop de titres maintenus | Coûts fixes et QA multipliés | Un titre validé avant portefeuille |

La simplification économique des sources de revenu ne doit pas masquer les contraintes de distribution. Apple impose des conditions pour les achats de biens numériques et demande notamment la divulgation des probabilités pour les objets aléatoires achetés. Ce plan évite les loot boxes et les mécanismes de hasard payant. Les choix précis restent à vérifier avant publication. [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/).

Pour la publicité en EEE/UK/Suisse, intégrer les exigences applicables de consentement, dont celles de Google sur les CMP certifiées. Sur iOS, vérifier ATT si les données sont utilisées pour le suivi entre applications et sites. Le refus d’un consentement ne doit pas être contourné ; il peut aussi modifier mesure et rendement publicitaire. [Google CMP](https://support.google.com/admob/answer/13554020), [Apple données et confidentialité](https://developer.apple.com/app-store/user-privacy-and-data-use/).

## 13. Plan de lancement et décisions d’arrêt

L’objectif est d’acheter progressivement de l’information, sans engager tout le budget avant d’avoir vu jouer de vrais utilisateurs.

### Étape A — deux concepts très courts

Durée indicative : 20–40 heures au total, 100–300 € cash. Un mécanisme jouable par concept, pas de progression profonde, pas de système de skins complet. Observer 15–30 joueurs extérieurs au projet : compréhension, plaisir, envie de relancer et éléments montrables dans une vidéo.

Choisir un seul concept. Arrêter ceux qui ne sont pas compris ou ne donnent pas envie de rejouer après deux améliorations ciblées. Le jugement de quelques testeurs n’est pas une mesure statistique du potentiel commercial, mais évite de financer des problèmes évidents.

### Étape B — version instrumentée et premier lancement limité

Atteindre le total cible de 250 heures de création/lancement si le concept mérite de continuer. Plafond de création cash 1 800 €. Inclure sauvegarde, tutoriel court, contrôle des erreurs, mesure de rétention, monétisation limitée et parcours d’achat fiable.

Prévoir les délais des comptes et boutiques. Certains nouveaux comptes personnels Google Play doivent notamment effectuer un test fermé avec 12 testeurs inscrits en continu pendant au moins 14 jours avant de demander l’accès à la production. Ce n’est pas une garantie d’approbation à J14. [Exigences Google Play](https://support.google.com/googleplay/android-developer/answer/14151465).

### Étape C — 500 à 1 000 installations de test

Budget média de découverte : 500–1 000 €, à couper par lots. Ajouter environ 300–600 € de frais fixes/créations jusqu’à la première décision, selon la durée. **Plafond cash recommandé avant preuve : environ 3 000–3 500 €**, hors matériel majeur et vie personnelle. Les 1 800 € de création et les campagnes font partie de cette enveloppe, ils ne viennent pas s’y ajouter à nouveau.

Tableau de décisions proposé pour ce petit casual, à ajuster au genre et aux cohortes :

| Mesure | Continuer / améliorer | Arrêt ou refonte |
|---|---|---|
| Compréhension du premier niveau | Joueurs capables d’agir sans explication externe | Confusion persistante malgré corrections |
| D1 | Chercher au moins ~30 % | Sous ~20 % après deux itérations et stabilité technique vérifiée |
| D7 | Chercher au moins ~8 % | Sous ~4 % persistant sur cohortes suffisamment mûres |
| D30 | Chercher au moins ~2 % pour prolonger l’étude | Absence de retour durable, pas de progression crédible |
| Stabilité | Viser ≥99,5 % de sessions sans crash | Corriger avant toute augmentation média |
| Achats | Livraison/restauration contrôlées, peu d’incidents | Toute défaillance systémique suspend la vente |
| Acquisition | Contribution prudente / CPI >1,3 sur le même segment | Ratio <1 : ne pas augmenter le budget pour « compenser » |

Les seuils de rétention sont des **portes d’apprentissage**, pas des preuves de rentabilité. Notre scénario central les approche et demeure pourtant économiquement peu attractif.

À 1 000 installations et 1 % de payeurs, on n’attend que dix acheteurs : c’est trop peu pour extrapoler tranquillement un catalogue IAP. Pour une rétention de 30 %, l’incertitude d’échantillonnage indicative à 1 000 joueurs est d’environ ±2,8 points à 95 % sous approximation binomiale ; à 500 joueurs elle est proche de ±4 points. Les biais de sélection, pays et campagnes s’ajoutent. Ne pas conclure sur deux achats élevés ou des proches très engagés.

### Étape D — augmenter seulement un jeu démontré

Attendre des cohortes assez âgées et des revenus réconciliés avec les dashboards pour estimer D90/D180. Les extrapolations doivent être conservatrices. Sur un premier titre, limiter la montée des dépenses avant ces preuves ; financer éventuellement un peu de collecte supplémentaire, pas une croissance massive.

Si les conditions favorables se confirment : augmenter par paliers, réestimer la LTV du nouveau segment, contrôler les décaissements et préparer environ 8 000 € de liquidité de projet dans notre exemple. Revoir le plan dès que le CPI, la rétention ou le support dévient.

## 14. Tableau de bord d’exploitation

À instrumenter dès le lancement : premier lancement, fin tutoriel, début/fin/échec de niveau, durée de session, demandes et impressions publicitaires, revenu publicitaire attribuable, achat initié/validé/livré/remboursé, restauration et version du jeu.

Chaque semaine :

- Par OS/pays/canal/cohorte : installations, CPI, D1/D7/D30, journées actives, recette pub, IAP nets et contribution cumulée.
- Produit : taux de fin tutoriel, abandons par niveau, sessions sans crash et temps de chargement.
- Monétisation : vidéo acceptée → servie, prix observés, conversion par produit, achats par payeur, remboursements et incidents.
- Finances : dépenses média, créations, outils, heures, revenus gagnés, versements reçus et trésorerie disponible.

Conserver séparément achats de test, bots/fraude et installations de développement. Réconcilier les revenus analytiques avec ceux des plateformes, qui peuvent être ajustés ultérieurement. Les tests A/B doivent garder un indicateur de rétention et de satisfaction ; optimiser uniquement l’ARPDAU publicitaire peut dégrader la valeur de cohorte.

## 15. Faut-il générer plusieurs jeux ?

Une bibliothèque de composants, outils de test, intégrations et modèles d’assets réduit les coûts suivants. Mais les joueurs ne sont pas transférables à l’infini entre jeux, et chaque titre demande une page boutique, des créations, du support et des mises à jour.

Exemple de portefeuille **sans prétendre connaître le taux de succès** : un jeu produit le favorable de notre modèle, deux prototypes sont abandonnés après 1 000 € et 60 heures chacun. Le résultat cash global devient environ **20 567 €**. Après le temps valorisé, le résultat économique du portefeuille devient **−1 333 €**, contre +4 267 € pour le titre gagnant seul. Les essais ratés comptent.

On peut écrire une espérance avec un taux de succès hypothétique, mais aucun taux fiable n’a été établi pour ton profil. Le plan n’en invente pas. Commencer avec une enveloppe d’expérimentation plafonnée et tenir le registre de **tous** les essais, y compris non publiés.

## 16. Recommandation finale et usage du modèle

**Avis : investissement expérimental intéressant, source de revenu régulière non démontrée.** Un jeu casual hybride est un meilleur premier test qu’un jeu dépendant uniquement de skins ou une série de clones publicitaires. La décision d’investir davantage doit être conditionnée à la contribution de cohorte et à une voie d’acquisition reproductible.

Ordre proposé : un concept validé par observation, un lancement limité, une mesure propre, puis un budget augmenté. Avant preuve, environ **3 000–3 500 € maximum de cash projet** et une enveloppe d’heures explicite. Ne pas prévoir de vivre des revenus du scénario favorable.

Le classeur `MODELE_FINANCIER_JEUX_MOBILES.xlsx` accompagne ce plan dans `outputs/mobile-business-20260906/`. Il contient : synthèse, hypothèses, calcul des cohortes, trois prévisions mensuelles, sensibilités et sources.

Pour l’adapter :

1. Modifier les prix, achats, rétention, délai de paiement et valeur du temps dans les hypothèses.
2. Modifier les volumes organiques et budgets payés mois par mois ; conserver zéro quand aucun canal ne les justifie.
3. Ajuster eCPM, livraison des pubs, CPI et coûts dans les grilles mensuelles. Les indicateurs de LTV de référence supposent les paramètres de cohorte stables ; après changement mensuel, ne pas les lire comme une prévision exacte de cette nouvelle campagne.
4. Contrôler que les parts IAP totalisent 100 % et que la courbe de rétention ne comporte pas d’augmentation accidentelle. Adapter la méthode si les données réelles ont une autre forme.
5. Lire le résultat économique et le besoin de trésorerie, pas seulement la recette de M12.

Le calcul par cohortes a été réconcilié avec une simulation journalière indépendante. Les effets d’un changement d’installations en M12, de commission, de coût de création, de délai de versement et de zéro achat ont été testés. La mise en page des feuilles et le graphique ont été contrôlés. Cela valide le fonctionnement des calculs sur ces cas, **pas les hypothèses de performance commerciale**.

Limites explicites : pas de prévision fiscale personnelle, pas de probabilités de succès, pas d’inflation/FX, pas de différence comportementale payé/organique, pas de valeur terminale, pas de saisonnalité des eCPM par défaut, pas de simulation causale de l’effet des publicités sur la rétention. Les chiffres de douze mois n’incluent pas les recettes futures encore possibles des cohortes récentes ; les LTV ne sont donc pas à multiplier naïvement par les installations annuelles pour obtenir les recettes de la même année.
