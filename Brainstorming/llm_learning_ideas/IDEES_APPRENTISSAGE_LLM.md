# Révolutionner le développement des LLM : pistes de recherche

Document de brainstorming (2026-11-15 et 2026-11-16). Deux parties :

1. Panorama des pistes (pré-entraînement frugal, apprentissage continu, sommeil et rêves) avec notation.
2. Apprentissage rapide : mettre à jour les poids à partir de peu de données, comme le cerveau.

Les chiffres cités viennent surtout de résumés et de préprints que je n'ai pas ouverts en entier : à vérifier avant de s'appuyer dessus.

---

# Partie 1 : panorama des pistes

Tes trois intuitions (pré-entraînement frugal, apprentissage continu par usage et feedback, système de "rêves" hors inférence) correspondent à des axes de recherche déjà actifs en 2026. La combinaison la plus crédible à court terme est : journal d'expériences le jour, consolidation hors ligne la nuit dans des adaptateurs épars, validation avant de committer les poids.

## Les pistes

**Tes idées, telles qu'elles existent déjà**

1. **Sommeil et rêves (consolidation hors ligne)** : deux papiers de 2026 s'intitulent "Language Models Need Sleep". L'un convertit le contexte récent en poids rapides, puis vide le cache d'attention. L'autre, lié à Google, ajoute une phase de "rêve" où le modèle génère son propre curriculum synthétique (AIME-24 de 73,8 à 79,2 sur Qwen3-8B, chiffre rapporté de seconde main).
2. **Apprentissage continu par mises à jour éparses** : on ne modifie que des paramètres ciblés (couches mémoire clé-valeur, adaptateurs type LoRA) pour limiter l'oubli catastrophique.
3. **Apprentissage par feedback d'usage** : mise à jour des poids à partir des retours utilisateurs. Aucun système de production ne le fait automatiquement, car les mises à jour naïves dégradent les capacités existantes.
4. **Pré-entraînement frugal en données** : le challenge BabyLM impose des budgets de données à échelle humaine (curriculum, tokenisation apprise, repondération des données). Les gains restent modestes : un résultat auto-déclaré montre que 4x plus de pas d'optimisation bat un changement d'architecture.

**Pistes voisines**

5. **Test-time training et poids temporaires** : le modèle s'ajuste pendant l'inférence, sans toucher aux poids de base (TTT-Discover, ReGrad qui récupère des gradients pré-calculés par document).
6. **Mémoire multi-échelles** : Titans et Nested Learning/HOPE (Google) traitent la mémoire comme un spectre de modules mis à jour à des fréquences différentes. Il n'y a ni code ni poids officiels, seulement des reproductions à échelle réduite.
7. **Auto-édition (type SEAL)** : le modèle écrit ses propres données et consignes de fine-tuning.
8. **Raisonnement latent et modèles récursifs** : raisonner dans un espace continu plutôt que token par token (JEPA-Reasoner, et de mémoire les Tiny Recursive Models de quelques millions de paramètres, non revérifiés ici).
9. **Objectifs prédictifs latents (JEPA pour le langage)** : prédire des représentations plutôt que des tokens, pour des représentations plus denses avec moins de données.
10. **Diffusion de texte** : plusieurs tokens par passe (Mercury, Nemotron-Labs-Diffusion, environ 6x tokens par passe selon NVIDIA). Le gain est surtout en vitesse.
11. **Mémoire en espace texte** : fichiers mémoire et contexte géré par l'agent. C'est la pratique actuelle, mais un benchmark de juillet 2026 conclut que le prompt seul échoue dans la plupart des régimes.
12. **Règles d'apprentissage locales (hebbien, sans backprop)** : la plus proche de ton "renforcer les liaisons neuronales", et la moins prouvée à l'échelle.

## Notation

Notes de 1 à 5 (5 = meilleur), total sur 25. Ce sont mes jugements, pas des mesures. "Sûreté" couvre l'oubli, la dérive et l'empoisonnement.

| # | Piste | Utilité | Preuves | Facilité | Petits modèles | Sûreté | Total |
|---|---|---|---|---|---|---|---|
| 11 | Mémoire en espace texte | 3 | 5 | 5 | 5 | 4 | **22** |
| 1 | Sommeil et rêves | 5 | 3 | 3 | 5 | 4 | **20** |
| 4 | Pré-entraînement frugal | 4 | 2 | 4 | 5 | 5 | **20** |
| 2 | Mises à jour éparses | 4 | 3 | 4 | 5 | 3 | **19** |
| 5 | Test-time training | 4 | 4 | 3 | 4 | 4 | **19** |
| 8 | Raisonnement latent, récursif | 4 | 3 | 3 | 5 | 4 | **19** |
| 9 | JEPA langage | 4 | 2 | 2 | 4 | 5 | 17 |
| 10 | Diffusion de texte | 3 | 4 | 2 | 3 | 5 | 17 |
| 6 | Mémoire multi-échelles | 5 | 2 | 2 | 4 | 3 | 16 |
| 7 | Auto-édition (SEAL) | 4 | 3 | 2 | 3 | 2 | 14 |
| 12 | Règles locales sans backprop | 3 | 1 | 2 | 4 | 4 | 14 |
| 3 | Feedback d'usage en ligne | 5 | 2 | 2 | 3 | 1 | 13 |

## Ce que j'en retiens

- **Le sommeil est la meilleure de tes trois idées.** Séparer l'apprentissage de l'inférence permet de valider les nouveaux poids avant de les adopter, ce qui neutralise le principal défaut du feedback en ligne (piste 3, dernière du tableau).
- **Les faits vont mal dans les poids.** Une étude de juillet 2026 mesure au mieux 46 % de rétention après 20 écritures séquentielles, et ces faits se composent mal en multi-sauts. Les poids conviennent mieux aux compétences et habitudes, la mémoire externe aux faits.
- **La mémoire texte n'est pas révolutionnaire, mais c'est la référence à battre.** Toute approche par les poids doit prouver qu'elle fait mieux qu'un bon fichier mémoire.
- **Prototype réaliste sur petit modèle** : un modèle de 0,5 à 3 Md de paramètres sur un seul GPU, avec journal d'épisodes, phase de sommeil (rejeu + rêves synthétiques + adaptateur épars) et test de non-régression avant commit. Cela combine les pistes 1, 2 et 11.

## Sources de la partie 1

- [When Does Continual Learning Require Learning](https://arxiv.org/pdf/2607.07847)
- [Continual Knowledge Updating in LLM Systems](https://arxiv.org/pdf/2605.05097)
- [What's continual learning and why might we expect to see it (LessWrong)](https://www.lesswrong.com/posts/5mCJzimtNZc9o4e26/what-s-continual-learning-and-why-might-we-expect-to-see-it)
- [Continual Learning: The Promised Land](https://humanoidhenry.substack.com/i/188306149/3-text-space-continual-learning-agentic-context-engineering)
- [Continual Learning via Sparse Memory Finetuning](https://www.pulse.bot/ai/blogs/continual-learning-via-sparse-memory-finetuning-72206da0-f286-490d-a80c-636d4d851ec0/)
- [Retrievable gradients (ReGrad)](https://themodelwire.com/article/retrievable-gradients-continual-post-training-without-cumulative-weight-drift-01KV73KWXTGY15H7M925A48XCF)
- [Language Models Need Sleep (2605.26099)](https://www.alphaxiv.org/abs/2605.26099v1)
- [Language Models Need Sleep: Learning to Self-Modify and Consolidate Memories (2606.03979)](https://www.emergentmind.com/papers/2606.03979.md)
- [Google Research: the sleep framework](https://research.google/blog/the-sleep-framework-a-new-way-for-llms-to-retain-knowledge-in-continual-learning/)
- [BabyLM Challenge](https://babylm.github.io)
- [Subword Segmental BabyLMs](https://arxiv.org/pdf/2609.01151)
- [Instanton baseline (model card)](https://huggingface.co/qyxu1994/instanton-baseline)
- [Google Research: Introducing Nested Learning](https://research.google/blog/introducing-nested-learning-a-new-ml-paradigm-for-continual-learning/?frame=0)
- [HOPE, reproduction non officielle](https://huggingface.co/smallhours19/nested-learning-hope)
- [JEPA-Reasoner (2512.19171)](https://www.arxiv.org/pdf/2512.19171)
- [DLLM-JEPA (2606.00091)](https://arxiv.org/abs/2606.00091)
- [JEPA vs Alternatives (wiki)](https://mishig-jepawiki.hf.space/wiki/concepts/jepa-vs-alternatives)
- [What Comes After LLMs? Mamba, Diffusion & World Models](https://glukhov.org/ai-models/architectures/what-comes-after-llms/)
- [Beyond transformers (N47)](https://n47.com/insights/beyond-transformers)

---

# Partie 2 : apprendre vite, comme le cerveau

Demande : l'apprentissage rapide à partir de peu de données est la clé, à la fois pour l'entraînement et pour la mémorisation. Le cerveau apprend vite parce qu'il n'utilise pas la même règle partout : une mémoire rapide écrit en un coup, et seulement quand ça compte, puis un système lent consolide. Voici les idées qui transposent ce principe aux poids d'un réseau.

## Briques déjà publiées

1. **Écriture en une passe par hyper-réseau** : Doc-to-LoRA (Sakana AI, ICML 2026) entraîne un petit réseau à produire directement l'adaptateur de poids à partir d'un document, en une seule passe avant, sans descente de gradient. C'est la preuve la plus solide qu'on peut "apprendre à écrire dans les poids". Code public (SakanaAI/doc-to-lora).
2. **Poids rapides à porte de surprise** : le Neuromodulated Delta Adapter (ESANN 2026) greffe sur un transformer gelé un module de rang faible, mis à jour par une règle delta de rang 1. Un détecteur de surprise méta-appris n'ouvre la fenêtre d'apprentissage que sur les erreurs confiantes.
3. **Plasticité hebbienne dans le transformer** : un papier d'octobre 2025 montre que la règle hebbienne neuromodulée domine en few-shot à supervision éparse, et que le gradient domine pour l'attribution de crédit à longue portée.
4. **Métaplasticité** : Palimpsa (ICML 2026) donne deux états à chaque synapse, pour une mémoire environ 5 fois plus durable. Le même travail note que des clés non orthogonales écrasent les souvenirs précédents.
5. **Le contexte est déjà une mise à jour de poids** : un papier théorique de Google montre que le contexte agit comme une mise à jour implicite de rang 1 du MLP. Cette mise à jour est dynamique et disparaît avec le contexte.

## Idées à tester (mes propositions, non prouvées)

6. **Écriture type BTSP** : en neurosciences, un potentiel de plateau déclenche un gros changement synaptique en un seul coup, sur une fenêtre de plusieurs secondes. Transposition : une trace d'éligibilité sur les derniers tokens, plus un signal "plateau" qui déclenche une seule grosse écriture. Je n'ai trouvé aucun résultat sur des benchmarks en réseaux artificiels : le terrain est ouvert.
7. **Figer l'apprentissage en contexte** : rendre persistante la mise à jour implicite de l'idée 5, en la calculant une fois puis en l'écrivant dans un adaptateur.
8. **Clés éparses orthogonalisées** : imiter la séparation de motifs de l'hippocampe pour que chaque souvenir écrive dans des paramètres presque disjoints. Cela attaque directement l'écrasement signalé par Palimpsa.
9. **Écriture dans le résidu seulement** : le cerveau intègre vite ce qui colle à ses schémas existants. On ne mettrait à jour que la partie de l'information que le modèle ne prédit pas déjà.
10. **Pré-entraînement pour la plasticité** : ajouter dès le pré-entraînement un objectif "être modifiable en un coup" (méta-apprentissage), au lieu de greffer la plasticité après.
11. **Mémoire rapide pendant l'entraînement** : un magasin clé-valeur absorbe les faits rares, et les poids lents n'apprennent que la structure. C'est mon pari le plus spéculatif pour réduire le besoin en données.

## Le prototype que je ferais

Un "hippocampe artificiel" sur un petit modèle gelé (moins de 1 Md de paramètres, un GPU) : adaptateur rapide de rang faible, porte de surprise, clés éparses, écriture delta en un coup (idées 2, 6, 8). Une phase de sommeil consolide ensuite vers un adaptateur lent.

Trois mesures suffisent pour savoir si ça vaut quelque chose :

- la rétention après une seule exposition ;
- l'interférence après N écritures ;
- l'écart avec un simple fichier mémoire ou du RAG.

## Sources de la partie 2

- [Doc-to-LoRA: Learning to Instantly Internalize Contexts (arXiv)](https://arxiv.org/abs/2602.15902)
- [Doc-to-LoRA (PMLR 306)](https://proceedings.mlr.press/v306/charakorn26a.html)
- [Sakana AI: Doc-to-LoRA et Text-to-LoRA](https://www.pulse.bot/ai/news/sakana-ai-introduces-doc-to-lora-and-text-to-lora-hypernetworks-that-instantly-internalize-long-cont-23bce215-aab0-48f8-b49a-fd56185f3f40/)
- [Neuromodulated Delta Adapter (ESANN 2026)](https://www.esann.org/sites/default/files/proceedings/2026/ES2026-143.pdf)
- [Hebbian and Gradient-Based Plasticity in Transformers](https://arxiv.org/abs/2510.21908v2)
- [Palimpsa (slides ICML 2026)](https://icml.cc/media/icml-2026/Slides/60823_ffOfTJ1.pdf)
- [Learning without training: The implicit dynamics of in-context learning](https://arxiv.org/pdf/2507.16003)
- [BTSP: A Burst in the Field of Learning and Memory](https://pubmed.ncbi.nlm.nih.gov/41224656/)
- [A simple model for BTSP provides content addressable memory](https://par.nsf.gov/biblio/10570625)
- [Rapid memory encoding in a recurrent network model with BTSP](https://www.aminer.org/pub/64a562aad68f896efab39758/rapid-memory-encoding-in-a-recurrent-network-model-with-behavioral-time-scale)
- [The brain as a blueprint: survey of brain-inspired learning](https://arxiv.org/pdf/2511.04455)
