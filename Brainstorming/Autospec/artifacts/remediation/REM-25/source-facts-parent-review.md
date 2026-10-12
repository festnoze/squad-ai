# Revue indépendante des faits source v0.2

Relecteur : coordinateur `/root`, 12 octobre 2026. Objet : extraction du contrat
avant toute génération ; aucune conformité d'un produit n'est jugée ici.

Documents lus intégralement, octets inchangés :

- `01_specification.md` — SHA256
  `0a99950df5ee132253fa5aefb1a8f6e4f7a4b64c1436072564be6d28195fb0f3`.
- `02_requirements_verification.md` — SHA256
  `efdab8ea54208557f01abcb5324172e42b9c5cf88536611d64ba65b92564cbf4`.
- Fichier approuvé `source-facts-v02.json` — SHA256
  `f2b3105f207cdf4d2feb7219535146e6890d838c7b4a93a4975c6ded040644b9`.

## Contrôles et décisions

1. `plan_limits` : les sept lots maximum sont explicites au §9 du brief. La
   limite porte sur les groupes de livraison, pas sur le nombre de tâches ou
   de stories. Les 57 IDs sont présents une fois chacun ; aucun nouvel ID ni
   nouveau verdict n'est créé. `acceptance_max_lots=7` doit être fourni
   explicitement et ne peut diverger du fait scellé.
2. `security_profile` : routes et préfixe issus de la table API ; statuts issus
   du §7 ; Argon2id 19 Mio/2 itérations/parallélisme 1, mots de passe 14–128,
   compteur dix échecs/60 s et session absolue 8 h/256 bits issus du §3. Les
   conversions 19 Mio → 19,456 Kio et 8 h → 28,800 s sont exactes. Le mode
   HTTP loopback exige l'exception explicite ; rien ne rend le métier public.
   Le seul défaut DB avec un statut imposé dans ce profil est `DB_BUSY=503`.
   Une faute DB arbitraire n'est pas contrainte artificiellement à 500/503.
3. `browser_profile` : timeout 15 s, bureau 1,280 px et mobile 390 px issus du
   §6. Six tickets client et douze personnel proviennent de FUN-02 du
   référentiel. Aucune formulation française exacte, sélecteur, texte de
   recherche ou marqueur de fixture n'est inventé comme obligation produit.
4. `quality_profile` : trois suites backend/frontend/E2E, backend 80% lignes
   et 70% branches, frontend 70% lignes, domaines sémantiques auth/services/
   permissions et auth/tickets/users/client HTTP sont explicites. Les seuils
   de durée restent des diagnostics, jamais des seuils éliminatoires ajoutés.
   Ni chemins source, ni framework de tests, ni noms de scripts ne sont
   imposés par ces catégories.
5. Les quinze ancres correspondent aux sources exactes et rendent les
   dérivations visibles. Les attentes métier/architecture/opérations restent
   les 57 lignes sources, pas des valeurs constatées dans un produit. Les
   six E2E restent ceux de la section 8 du référentiel.
6. Exclusions vérifiées : secrets fictifs, bindings Python/SQL, sélecteurs,
   argv, node IDs, libellés résolus et longueur d'un token sont opérationnels,
   pas normatifs. En particulier, 256 bits ne signifie pas « 43 caractères ».
   La preuve d'entropie exige observation native et revue indépendante de sa
   propagation ; ce document n'est pas cette revue du futur produit.

Conclusion : **quatre faits approuvés, source seulement**. Les deux Markdown
normatifs ne sont pas modifiés. Les bindings et commandes du futur snapshot
exigeront leur proposition GPT et une seconde revue GPT distincte ; X/R/V ne
peuvent être déduits de cette approbation. Les tests d'import/généricité et le
raccord API strict passent dans `source-plan-api-root.xml` (68 PASS).
