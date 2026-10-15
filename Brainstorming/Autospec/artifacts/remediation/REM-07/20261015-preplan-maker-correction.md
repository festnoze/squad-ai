# REM-07 — correction maker PLAN bornée

## État

Implémentation terminée dans le worktree `codex/docker-template-locks` (base `cdf158a3`). La correction est disponible uniquement à la continuation pré-plan explicitement demandée par l’utilisateur. Le PLAN ordinaire conserve sa voie par défaut, sans auto-correction.

## Changements

- `_aplan_phase` accepte un opt-in strict `plan_maker_revision_limit=1` seulement avec le ticket du journal de continuation correspondant. L’option par défaut reste `0`.
- Avant tout appel provider dans ce mode, la continuation relit et vérifie le ticket courant : projet, continuation ID concordant, `explicit_request is True` dans le ticket et le journal, et ligne unique encore `UNKNOWN`. Cette lecture ne consomme pas la correction; un maker PLAN initial reste possible même si la correction unique a déjà été consommée.
- La continuation opt-in utilise le maker PLAN et le gate déterministe existants; elle n’appelle ni le pipeline PO avec reviewer, ni critic, ni judge. Elle ne lance au plus qu’une correction, fondée sur les erreurs exactes du gate; la réponse rejetée est citée comme donnée non fiable.
- Avant l’unique dispatch correctif, le journal superviseur enregistre durablement l’intention `UNKNOWN`, l’identité du contrat et les empreintes des deux reçus. Toute interruption consomme cette tentative. Le reçu initial du plan rejeté reste immuable.
- Une correction est refusée si le contrat ou la capture n’est pas vérifié, si le reçu manque, si la consommation/budget est inconnue ou épuisée, si un finding majeur indépendant reste ouvert, ou si une tentative a déjà été consommée.
- La réponse corrigée traverse le même gate complet. Un nouvel échec arrête la continuation sans créer de stories, sans fallback build et sans troisième appel.

## Vérifications

Tests hermétiques avec `FakeRunner`; aucun vrai fournisseur ou produit généré n’a été appelé/modifié. Le lot couvre le succès après correction, la persistance de `UNKNOWN` avant le second appel, l’échec persistant, budget épuisé, coût non réconcilié, finding non réparable, répétition sur une seconde continuation, et maintien du comportement default-off.

Commande exécutée depuis la racine du worktree :

```powershell
& 'C:\Users\e.millerioux\.codex\worktrees\autospec-remediation-integration\squad-ai\Brainstorming\Autospec\backend\.venv\Scripts\python.exe' -m pytest -q --basetemp backend\_pytest-rem07-run7 backend\tests\test_plan_maker_correction_policy.py backend\tests\test_prebuild_resume.py backend\tests\test_plan_gates.py backend\tests\test_acceptance_pipeline_remediation.py backend\tests\test_plan_foundation_admission_diagnostics.py backend\tests\test_plan_pipeline.py
```

Résultat : **237 passed**. L’utilisation d’un `--basetemp` sous le worktree était nécessaire, car le répertoire temporaire Windows par défaut a refusé l’accès (`WinError 5`). `ruff` n’est pas installé dans cet environnement (`No module named ruff`).

## Limites

Le budget disponible est une estimation du budget projet, pas un plafond financier imposé au fournisseur. Aucune génération payante n’a servi à démontrer le comportement; les tests prouvent le raccord et les refus avec des reçus synthétiques, pas la qualité d’une réponse réelle. Les findings majeurs indépendants demeurent bloquants et requièrent leur traitement hors de cette correction maker-only.
