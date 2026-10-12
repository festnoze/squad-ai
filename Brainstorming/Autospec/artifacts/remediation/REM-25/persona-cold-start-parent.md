# Initialisation froide des personas en campagne

La contre-revue indépendante a lancé le test nominal QA seul dans un processus frais sur core `96af8140`. Il échouait avant la CLI : `_persona_role` parcourait aussi les rôles interdits et la validation de leur nom interrompait la construction. Les corpus plus larges avaient préchauffé cette table et masquaient le défaut ; les résultats antérieurs restent conservés avec cette limite.

La table est maintenant construite localement depuis les seuls noms admis dans le mode actif, puis publiée atomiquement. Elle est séparée par politique et rafraîchie à partir des personas courantes ; aucune construction partielle, aucun préchauffage générique requis. La validation du nom avant le cache reste inchangée et le mode générique garde tous ses rôles.

- `persona-cold-start-parent-v1.xml` : 47 PASS, 0,58 s, trois premiers rôles avec/sans préchauffage générique, échec de chargement atomique, corpus d'admission.
- `persona-cold-qa-parent-v1.xml` : test indépendant QA inchangé, lancé seul dans un processus frais, 1 PASS, 0,39 s. I/O CLI stubbées ; aucune inférence réelle, auth ou dépense.

Les deux URLs de transport des contre-tests API indépendants passent de `offline.test` à `127.0.0.1` pour atteindre la factory après l'ajout du Host boundary. Ni assertions ni code de production ne reçoivent une exception de test. Cette migration n'est pas une résolution silencieuse de l'échec QA froid : celui-ci est une correction source distincte.
