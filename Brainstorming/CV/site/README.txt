ETIENNE MILLERIOUX — SITE CV

Ouvrir index.html directement dans un navigateur : le site fonctionne sans installation et sans connexion internet.
Pour un aperçu local : python -m http.server 8000 --directory CV/site (depuis la racine Brainstorming).

Contenu : CV/data/*.js et CV/cv_full/data/experience_full.js.
Actualiser après un changement du CV :
  node CV/site/sync_data.cjs
  python CV/site/build_site.py

Design et responsive : styles.css.
Interactions, navigation, thèmes, modales et animation Canvas 2D : app.js.
Le CV imprimable est une copie autonome dans assets/cv.
Toutes les expériences du CV synthétique et les 15 missions détaillées sont reprises.
Les illustrations des réalisations sont des compositions graphiques, pas des captures des produits.

Direction graphique actuelle : bleu ardoise #1c2a48, ivoire #f7f8f2 et citron #dff68a.
Le thème sombre est présenté par défaut ; le choix du visiteur est conservé localement.
Les réalisations sont présentées en grandes séquences alternant illustration et texte.
