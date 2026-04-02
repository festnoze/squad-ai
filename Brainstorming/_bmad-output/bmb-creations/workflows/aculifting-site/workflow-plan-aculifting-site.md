---
stepsCompleted: ['step-01-discovery', 'step-02-classification']
created: 2026-02-13
status: CLASSIFICATION
---

# Workflow Creation Plan

## Discovery Notes

**User's Vision:**
Créer un workflow en deux phases majeures :
1. **Phase Recherche & Analyse** : Lancer un sous-agent pour rechercher et analyser au moins 5 sites web français sur l'aculifting via Playwright — contenu, structure et aspect graphique — et produire un rapport comparatif.
2. **Phase PRD** : À partir de cette analyse, rédiger un PRD complet en Markdown décrivant toutes les étapes de création d'un site web one-page HTML (SPA) pour la promotion des services d'aculifting.

**Who It's For:**
- **Praticienne** : Yamina Heinrich, spécialiste en Aculifting, techniques esthétiques non invasives
- **Localisation** : 622 avenue Xavier de Ricard
- **Contact** : 06 11 36 92 16 / yaminahinrich@yahoo.fr

**What It Produces:**
1. Un rapport d'analyse concurrentielle de 5+ sites d'aculifting français
2. Un PRD Markdown complet et modulaire pour la création du site one-page
3. Le site final sera un fichier HTML single-page, univers zen/bien-être

**Key Insights:**
- **Identité visuelle** : palette rose poudré/blush, doré/cuivré, blanc — style épuré, féminin, zen, élégant
- **Slogan** : "Redonnez éclat et jeunesse à votre visage naturellement"
- **Logo** : visage de profil stylisé avec aiguilles d'acupuncture dorées
- **Modularité** : tous les contenus (textes, images) doivent être facilement modifiables a posteriori via prompting
- **Objectifs du site** : acquisition clients, prise de contact, prise de rendez-vous en ligne

## Classification Decisions

**Workflow Name:** aculifting-site-builder
**Target Path:** _bmad/bmm/workflows/aculifting-site-builder/

**4 Key Decisions:**
1. **Document Output:** true (rapport d'analyse + PRD Markdown)
2. **Module Affiliation:** BMM (développement logiciel)
3. **Session Type:** continuable (multi-sessions, workflow complexe avec recherche web + analyse + rédaction)
4. **Lifecycle Support:** tri-modal (Create + Edit + Validate)

**Structure Implications:**
- Nécessite `steps-c/`, `steps-e/`, `steps-v/` (tri-modal)
- Nécessite `step-01b-continue.md` pour la reprise de session
- Tracking `stepsCompleted` dans le frontmatter des documents de sortie
- Dossier `data/` partagé entre les 3 modes
- Output format : free-form avec progression par étape
