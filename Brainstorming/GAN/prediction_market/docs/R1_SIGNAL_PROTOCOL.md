# R1 : Protocole figé avant la nouvelle extraction

Enregistré le 2026-09-13, avant téléchargement et lecture des résultats de la tranche 2024.
Identité exécutable : `signal-study.v1`. Une modification des seuils crée une nouvelle version et
compte comme une nouvelle recherche. Aucune optimisation de paramètres dans ce jalon.

## Corpus et calendrier

- Archive Polymarket déjà épinglée, 2024-01-01 inclus à 2024-07-01 exclu. Échantillon initial de
  1500 conditions par classement SHA256 indépendant des résultats, puis adaptateur binaire résolu.
- Réutiliser la projection CTF avant le bloc 60000000, dont l'horodatage vérifié est postérieur à
  cette fenêtre. Conserver inventaire, cas censurés, inconnus et exclusions.
- Étude sur le fold **train uniquement**. L'analyse ne demande aucune bande validation ou scellée.
  Le chargeur canonique vérifie néanmoins les fichiers et leur structure pour admettre le corpus ;
  cette vérification technique globale ne fournit aucune observation hors entraînement à l'étude.
  Exclure aussi les identifiants du fold scellé du corpus 2023, à partir de sa seule métadonnée.
- Observations entre le 2024-01-01 et le 2024-04-01, limitées mécaniquement à la borne d'entraînement
  du corpus si elle survient avant. Cibles et labels doivent être disponibles avant cette borne.
- Trois périodes descriptives : janvier, février, mars 2024. Les autres mois restent hors de cette
  étude. Une période incomplète ou sans observations reste explicitement identifiable.

## Hypothèses et observation par marché

Calibration : une seule observation, exactement 24 heures après le début de la bande horaire du marché,
sans choisir un instant d'après la résolution. Prix OUI dans les tranches [0;10[, [10;20[, …, [80;90[,
[90;100] %. Mesure en points de base : `résolution * 10000 - prix`. Présenter aussi probabilité moyenne
et fréquence gagnante. Ce gain d'une unité jusqu'à résolution est brut : ni frais, ni spread, ni
immobilisation du capital ne sont modélisés comme une exécution.

Retournements : pour les fenêtres de 24 et 48 heures, observer un mouvement d'au moins 300 pb jusqu'au
milieu de la fenêtre, puis un mouvement opposé d'au moins 300 pb jusqu'à sa fin. Tester séparément le
retournement haussier et baissier. Les trois prix de déclenchement doivent avoir du volume observé.
Conserver seulement le premier déclenchement causal de chaque variante par marché. Cible : variation
du prix 24 ou 48 heures après ce déclenchement, signée dans le sens du retournement. Exiger une barre
observée à l'horodatage exact ; ne jamais remplacer une cible manquante par le prochain prix disponible.

Activité : pour chaque hypothèse, publier l'ensemble et une condition fixée à l'avance : au moins
6 heures avec transactions dans les 24 dernières heures complétées ET dernier prix observé depuis
au plus 6 heures. La condition filtre l'ancre déjà choisie ; elle ne recherche pas un autre instant.
Les observations appartiennent aux deux groupes quand admissibles : ces groupes ne sont pas indépendants.

Cela représente **28 variantes** : (10 tranches + 2 fenêtres × 2 sens) × 2 conditions d'activité.
Tous les résultats sont conservés, même sans observation ou négatifs. Une observation manquante ne
devient pas zéro. Compter séparément les cibles au-delà de la borne temporelle, les cibles postérieures
à la résolution et celles sans transaction à l'heure exacte.

## Lecture des résultats

Minimum descriptif : 30 marchés avec cible et 3 semaines UTC distinctes. Regrouper les effets par
semaine de déclenchement et présenter un intervalle normal approximatif à 95 % de la moyenne des
moyennes hebdomadaires, séparément de la moyenne par marché. Ces intervalles ne sont ni corrigés pour
28 essais, ni une certification ; dépendances événementielles inconnues et faible nombre de blocs
limitent leur portée. R2 devra traiter la multiplicité et la réplication indépendante.

Critère de présélection descriptif fixé avant calcul : support minimum, couverture des cibles ≥80 %,
effet brut moyen >100 pb et effet positif dans chacun des trois mois. Sinon : « non retenu » ou
« indéterminé » si le support manque. Ce filtre n'établit pas une rentabilité nette ; 100 pb constitue
un seuil d'intérêt pour R2, pas une estimation des coûts réels.

Comparer la densité observée du nouvel adaptateur aux 29644/365980 heures du corpus 2023. Si elle
n'augmente pas, le constater sans sélectionner une autre période après examen des performances.
Livraison : protocole et empreintes, observations auditables, 28 lignes de résultats, couverture,
graphique de calibration et lecture par mois dans l'interface. Aucun passage automatique à R2.
