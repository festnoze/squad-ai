# Demos pedagogiques du projet NEAT Flappy Lab

## Objectif du projet

Ce projet est un laboratoire didactique pour comprendre progressivement plusieurs
idees centrales de l'apprentissage automatique:

- comment un modele simple fait une prediction;
- comment on mesure l'erreur d'une prediction;
- comment une fonction de loss transforme plusieurs erreurs en un seul score;
- comment la descente de gradient ajuste les parametres d'un modele;
- comment un reseau de neurones peut approximer une fonction non lineaire;
- comment NEAT explore une population de reseaux en modifiant a la fois les poids
  et la structure;
- comment comparer une approche par gradient descent et une approche evolutive.

L'objectif n'est pas seulement d'obtenir de bonnes performances, mais de rendre
les mecanismes visibles. Chaque demo doit donc montrer les concepts en action:
points de donnees, predictions, ecarts, evolution de la loss, modification des
poids, complexification du reseau, selection des meilleurs individus, etc.

## Parcours pedagogique

Les demos sont organisees comme une progression. On commence avec le cas le plus
simple, une droite, puis on ajoute progressivement de la complexite: reseau de
neurones, optimisation non lineaire, population de modeles, puis simulation
complete Flappy.

## Demo 1 - Regression lineaire

### Idee principale

La regression lineaire cherche la meilleure droite possible pour approximer des
points de donnees.

Le modele est:

```txt
y_pred = w * x + b
```

Avec:

- `x`: entree;
- `y`: valeur reelle observee;
- `y_pred`: prediction du modele;
- `w`: pente de la droite;
- `b`: biais, ou ordonnee a l'origine.

### Concepts abordes

- Prediction d'un modele simple.
- Difference entre valeur reelle et valeur predite.
- Residus visuels entre les points et la droite.
- Fonction de loss MSE:

```txt
loss = moyenne((y_pred - y)^2)
```

- Descente de gradient sur deux parametres: `w` et `b`.
- Role du learning rate.
- Effet du bruit dans les donnees.
- Difference entre convergence stable, convergence lente et oscillation.

### Ce que la demo doit rendre visible

- Les points de donnees.
- La droite initiale.
- La droite courante.
- Les segments d'erreur entre chaque point et la prediction correspondante.
- La loss en temps reel.
- Les valeurs courantes de `w`, `b`, `loss` et du nombre d'iterations.
- L'impact des parametres modifiables: learning rate, bruit, vitesse, seed.

## Demo 2 - Reseau de neurones pour approximer une fonction quadratique

### Idee principale

Une droite ne peut pas bien approximer une fonction courbe. On introduit donc un
petit reseau de neurones capable de produire une prediction non lineaire.

La demo utilise un reseau simple:

```txt
1 entree -> neurones caches tanh -> sortie lineaire
```

Les neurones caches transforment l'entree avec des fonctions non lineaires. La
sortie combine ces activations pour produire une courbe.

### Concepts abordes

- Limite d'un modele lineaire.
- Approximation de fonction non lineaire.
- Neurones caches et activations.
- Poids entre entree, couche cachee et sortie.
- Forward pass: calcul de la prediction.
- Backpropagation: calcul des gradients.
- Optimisation des poids par descente de gradient ou optimiseur adaptatif.
- Evolution de la prediction au fil des iterations.

### Ce que la demo doit rendre visible

- Les points issus d'une fonction quadratique bruitee.
- La courbe de prediction du reseau.
- Les residus entre les points et la courbe.
- La loss en temps reel.
- Les activations de certains neurones caches.
- Les poids du reseau sous forme visuelle.
- L'effet du learning rate, du nombre de neurones caches, du bruit et de la seed.

## Demo 3 - Mini-NEAT interactif

### Idee principale

La descente de gradient optimise les poids d'un modele donne. NEAT va plus loin:
il fait evoluer une population de reseaux, et peut modifier progressivement leur
structure.

NEAT signifie:

```txt
NeuroEvolution of Augmenting Topologies
```

L'idee est de commencer avec des reseaux simples, puis d'ajouter des connexions
ou des neurones lorsque les mutations structurelles sont utiles.

### Concepts abordes

- Population d'individus.
- Fitness.
- Selection des meilleurs individus.
- Mutation des poids.
- Mutation structurelle.
- Complexification progressive.
- Especiation pour proteger les innovations.
- Difference entre apprendre par gradient et explorer par evolution.

### Ce que la demo doit rendre visible

- Une population de candidats.
- La fitness des individus.
- Les meilleurs individus qui influencent la generation suivante.
- L'evolution de l'erreur du meilleur individu.
- La diversite des especes.
- La complexite moyenne ou maximale des genomes.
- L'effet du taux de mutation et de la taille de population.

## Demo 4 - Flappy Lab

### Idee principale

La demo Flappy applique les concepts precedents dans une simulation plus riche:
une population d'oiseaux est pilotee par des reseaux de neurones qui apprennent a
survivre dans un environnement de type Flappy.

Chaque oiseau est controle par un reseau. Les entrees du reseau decrivent l'etat
du monde, par exemple:

- distance verticale au prochain trou;
- distance horizontale au prochain obstacle;
- vitesse verticale;
- position de l'oiseau;
- informations sur le prochain obstacle.

La sortie du reseau decide si l'oiseau saute ou non.

### Concepts abordes

- Controle par reseau de neurones.
- Fitness basee sur la survie.
- Evaluation d'une population dans le meme environnement.
- Selection, mutation, crossover et especiation.
- Comparaison entre regimes:
  - evolution pure;
  - gradient descent;
  - hybridation;
  - confrontation NEAT vs GD.
- Visualisation d'un genome et de ses activations.

### Ce que la demo doit rendre visible

- Les oiseaux en simulation.
- Le reseau de l'oiseau selectionne.
- Les activations du reseau en temps reel.
- Les courbes de fitness.
- La complexite du meilleur reseau.
- Le classement des individus.
- La comparaison entre camps ou modes d'apprentissage.

## Fil conducteur conceptuel

Le parcours suit une progression volontaire:

1. **Prediction simple**: une droite produit une prediction.
2. **Erreur**: on mesure l'ecart entre prediction et realite.
3. **Loss**: on resume toutes les erreurs en un seul nombre.
4. **Gradient**: on ajuste les parametres pour faire baisser la loss.
5. **Non-linearite**: un reseau peut approximer des formes plus complexes.
6. **Population**: plusieurs modeles peuvent etre explores en parallele.
7. **Evolution**: selection et mutation permettent de chercher sans gradient.
8. **NEAT**: la structure du reseau peut elle aussi evoluer.
9. **Simulation**: les concepts sont appliques a un probleme dynamique.

## Principes de conception des demos

Chaque demo doit respecter quelques principes:

- montrer les donnees et les predictions;
- rendre l'erreur visible, pas seulement numerique;
- afficher la loss et son evolution;
- exposer les parametres importants;
- permettre de ralentir, avancer pas a pas et reinitialiser;
- privilegier les explications visuelles aux textes longs;
- garder les anciennes demos accessibles pendant que les suivantes sont explorees.

## Extensions possibles

Quelques ameliorations pedagogiques possibles:

- Ajouter un mode "step pedagogique" qui separe prediction, erreur, loss,
  gradient et mise a jour.
- Ajouter une selection de point pour inspecter son erreur individuelle.
- Ajouter une visualisation du paysage de loss pour la regression lineaire.
- Comparer MSE et MAE pour expliquer l'impact des outliers.
- Ajouter des presets de learning rate.
- Ajouter une comparaison directe entre regression lineaire et reseau non
  lineaire sur le meme dataset.
- Montrer explicitement les mutations NEAT sur un genome avant/apres.
- Ajouter un replay d'une generation Flappy pour comparer plusieurs strategies.

## Intention finale

Le projet doit permettre a quelqu'un qui ne connait pas NEAT de construire son
intuition par etapes:

```txt
prediction -> erreur -> loss -> gradient -> reseau -> population -> evolution -> NEAT
```

La priorite est donc la comprehension operationnelle: voir ce qui change, quand
cela change, et pourquoi cela ameliore ou degrade le comportement du modele.

