# Guide Prospector : utilisation et fonctionnement

Prospector est un système semi-autonome de prospection de missions freelance
full-remote en ingénierie IA (AI Engineer, Forward Deployed Engineer, GenAI,
LLM, RAG). Il cherche des missions, les note, rédige des candidatures
personnalisées (FR/EN) avec le bon CV en PDF, puis attend votre validation
avant tout envoi.

Principe fondamental : **rien ne part sans votre approbation explicite**.

---

## Partie 1 : Comment l'utiliser

### 1.1 Installation (une seule fois)

Tout se passe dans `C:\Dev\squad-ai\Brainstorming\Prospector`.

**Étape 1 : environnement Python** (déjà créé ; à refaire seulement si besoin)

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\playwright install chromium
```

La dernière commande télécharge le navigateur utilisé pour parcourir les
plateformes et générer les PDF (fallback). Elle n'a pas encore été lancée
(téléchargement volumineux) : **c'est à faire avant le premier `/prospect` complet**.

**Étape 2 : compte Gmail dédié**

1. Créer le compte Gmail réservé à la prospection.
2. Activer la validation en deux étapes (2FA).
3. Générer un « mot de passe d'application » : Compte Google > Sécurité >
   Mots de passe d'application.
4. Configurer le projet :
   ```powershell
   copy .env.example .env
   ```
   puis remplir dans `.env` : `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`
   (et `DAILY_EMAIL_CAP`, plafond d'envois par jour, 5 par défaut).
5. Renseigner aussi l'adresse dans `config\profile.yaml`, champ `identity.email`.

**Étape 3 : connexions aux plateformes** (une fois par plateforme)

```powershell
venv\Scripts\python.exe scripts\login_setup.py --site malt
venv\Scripts\python.exe scripts\login_setup.py --site linkedin
# idem : upwork, comet, freework, lehibou, wttj, contra
```

Une fenêtre de navigateur s'ouvre : connectez-vous manuellement, puis fermez la
fenêtre. La session est conservée dans `browser_profile\` et réutilisée par les
agents (en lecture seule). Si une session expire plus tard, relancez simplement
la même commande.

**Étape 4 : les PDF de CV**

Déjà générés dans `assets\cv\` (4 variantes : `cv_fr_short`, `cv_fr_full`,
`cv_en_short`, `cv_en_full`). À régénérer après toute modification des sources
dans `cv\` avec la commande `/cv-refresh` (ou
`venv\Scripts\python.exe scripts\render_cv.py`).

### 1.2 Utilisation quotidienne

Ouvrir un terminal **dans le dossier Prospector** et lancer `claude` (les
agents et skills du projet ne sont chargés que depuis ce dossier).

| Commande | Rôle |
|---|---|
| `/prospect` | Cycle complet : recherche sur toutes les sources, scoring, rédaction des brouillons dans la file d'attente |
| `/review` | Passage en revue des brouillons : approuver / modifier / rejeter chacun |
| `/dispatch` | Envoi des candidatures approuvées (emails automatiques, plateformes préremplies pour votre clic final) |
| `/follow-up` | Détection des réponses + rédaction des relances (max 2, espacées de 5 jours min) |
| `/cv-refresh` | Régénération des 4 PDF de CV |

**Routine type du matin :**

1. `/prospect` : le système chasse et rédige (10 à 15 minutes, autonome).
2. `/review` : vous validez chaque brouillon en quelques secondes
   (approuver, demander une retouche, ou rejeter en donnant la raison).
3. `/dispatch` : les emails partent (avec le CV joint, plafonné par jour),
   les candidatures plateformes s'ouvrent préremplies dans le navigateur et
   **vous cliquez vous-même sur « Envoyer »**.
4. `/follow-up` de temps en temps (tous les 2-3 jours suffisent).

Les lancements sont manuels par choix. Le jour où vous voulez automatiser la
découverte, le Planificateur de tâches Windows peut lancer
`claude -p "/prospect"` chaque matin : tout est déjà prêt pour ça.

### 1.3 Régler le comportement

Trois fichiers de configuration, modifiables à tout moment :

- `config\targets.yaml` : sources activées/désactivées, requêtes de recherche
  FR/EN, seuil de score minimal (0.6), plafonds (10 brouillons par run,
  5 emails par jour, 2 relances max).
- `config\profile.yaml` : votre vérité candidat. Titres visés, compétences
  pondérées, TJM (800 € exécution / 1 100 € formation / 1 200 € conseil,
  600 € plancher), règles géographiques et de langue, réalisations mises en
  avant dans les lettres. C'est LA source des faits : les agents n'ont pas le
  droit d'affirmer quoi que ce soit qui n'y figure pas (ou dans les CV).
- `config\style.md` : règles d'écriture des messages (longueurs, structure,
  interdits, exemples FR et EN).

Bonus : chaque rejet dans `/review` alimente `config\review-feedback.md` avec
votre raison. Le rédacteur relit ce fichier aux runs suivants : le système
apprend vos goûts.

---

## Partie 2 : Comment ça fonctionne

### 2.1 Vue d'ensemble du pipeline

```
        /prospect
            |
   +--------+--------+-----------------+----------------+
   v                 v                 v                v
scout-boards   scout-platforms   scout-linkedin   scout-direct
(APIs/RSS +    (Malt, Upwork...  (LinkedIn, WTTJ, (entreprises a
 recherche      via session       Indeed)          contacter en
 web)           enregistree)                       spontane)
   |                 |                 |                |
   +--------+--------+-----------------+----------------+
            v
   data\prospector.db  (SQLite : deduplication, statuts, historique)
            |
            v
         scorer        (score 0-1 contre profile.yaml, filtres durs)
            |
            v
         writer        (message sur mesure FR/EN + choix canal + choix CV)
            |
            v
   data\queue\pending\   <-- un fichier .md par candidature
            |
            v
        /review        (VOUS : approuver / modifier / rejeter)
            |
            v
   data\queue\approved\
            |
            v
       /dispatch       (email auto plafonne, plateforme = preremplissage + votre clic)
            |
            v
   data\queue\sent\  +  suivi des reponses (/follow-up, relances, stats)
```

### 2.2 La découverte (4 agents éclaireurs, en parallèle)

- **scout-boards** : interroge les APIs publiques sans connexion (RemoteOK,
  Remotive, flux RSS WeWorkRemotely) via `scripts\fetch_boards.py`, puis
  complète par des recherches web ciblées avec les requêtes de `targets.yaml`.
- **scout-platforms** : parcourt les plateformes freelance avec la session
  enregistrée dans `browser_profile\` (Playwright). Filtres : full remote +
  mots-clés IA. **Lecture seule** : il ne postule jamais, ne clique jamais
  « postuler » (respect des CGU, protection de vos comptes).
- **scout-linkedin** : même principe sur LinkedIn Jobs (filtres Remote +
  Contract), Welcome to the Jungle et Indeed.
- **scout-direct** : cherche des entreprises à contacter en candidature
  spontanée. Exigence : un signal « pourquoi maintenant » documenté (levée de
  fonds, recrutements IA répétés, projet GenAI annoncé). Seuls les contacts
  professionnels publics sont retenus (conformité RGPD).

Chaque mission trouvée est insérée dans SQLite avec un hash calculé sur l'URL
normalisée (ou titre + entreprise) : une mission déjà vue est ignorée
automatiquement, donc jamais de double candidature.

### 2.3 Le scoring

L'agent **scorer** applique d'abord des filtres éliminatoires :

- pas full-remote -> éliminé ;
- règle langue/géo violée -> éliminé (France = candidature en français ;
  UK/USA/environnement anglophone = candidature en anglais ; le reste = hors
  cible) ;
- CDI uniquement, stage, temps partiel -> éliminé.

Puis un score pondéré (0 à 1) pour les survivantes :

| Composante | Poids | Ce qui est mesuré |
|---|---|---|
| Titre | 0.30 | correspondance avec les titres visés (profile.yaml) |
| Stack | 0.30 | recouvrement compétences mission / compétences pondérées |
| Séniorité | 0.15 | poste senior/lead attendu ou non |
| Tarif | 0.15 | compatibilité TJM (plancher 600 €) |
| Contexte | 0.10 | bonus différenciateurs (EdTech, évals, AI Act, FDE) |

Les red flags (spam de staffing, TJM trop bas, profil junior attendu...)
retirent des points. Seules les missions au-dessus du seuil (0.6 par défaut)
passent au rédacteur. Le détail du calcul est conservé en base pour chaque
mission (transparence du score).

### 2.4 La rédaction

L'agent **writer** produit un brouillon par mission qualifiée, en choisissant :

- **le canal** : message plateforme, email (si un contact public existe),
  message LinkedIn, ou formulaire ;
- **la langue** : celle imposée par la règle géo de la mission ;
- **le CV** : version courte par défaut, version complète pour les ESN ou si
  l'offre demande un dossier détaillé.

Le message suit `config\style.md` : 120-180 mots pour un email, ouverture sur
LEUR besoin concret, 2-3 réalisations réelles choisies dans `profile.yaml`
selon la mission, un seul appel à l'action (un échange de 20 minutes), zéro
formule d'IA générique, zéro fait inventé.

Chaque brouillon est un fichier markdown dans `data\queue\pending\` avec un
en-tête YAML (mission, score, canal, langue, CV choisi, destinataire, sujet)
suivi du message exact qui serait envoyé. Lisible et modifiable à la main si
vous préférez.

### 2.5 La validation et l'envoi

- `/review` vous présente chaque brouillon (mission, score, destinataire,
  message intégral) et attend votre décision. Approuvé -> `approved\`.
  Rejeté -> `rejected\` + raison enregistrée pour améliorer les runs suivants.
- `/dispatch` traite `approved\` :
  - **email** : envoi réel via Gmail SMTP (`scripts\send_email.py`), CV en
    pièce jointe, copie cachée à vous-même. Le plafond quotidien est vérifié
    **dans le code** (refus avec code d'erreur si atteint), pas seulement dans
    les instructions des agents.
  - **plateforme/LinkedIn/formulaire** : le navigateur s'ouvre sur la mission,
    le message est prérempli, le CV uploadé si possible, et le clic final est
    le vôtre. C'est le compromis qui automatise 95 % du travail sans jamais
    violer les CGU ni risquer un bannissement de compte.
- Tout envoi est archivé dans `sent\` et tracé en base (date, canal, CV).

### 2.6 Le suivi

- `scripts\check_replies.py` scanne la boîte Gmail en IMAP et rapproche les
  réponses des candidatures envoyées ; une réponse positive passe la mission
  au statut `interview` et remonte en tête de rapport.
- `/follow-up` rédige les relances des candidatures restées sans réponse
  (délai 5 jours, maximum 2 relances, 40-70 mots, un élément nouveau à chaque
  fois). Les relances repassent par la même file de validation que tout le
  reste.
- `scripts\report.py` produit le digest : nouvelles missions par source,
  meilleures missions non traitées, état de la file, envois de la semaine,
  réponses, relances dues.

### 2.7 Cycle de vie d'une mission (états en base)

```
new -> scored -> drafted -> queued -> sent -> replied -> interview -> won | lost
                                  (ignored : éliminée par le scorer ou rejetée par vous)
```

### 2.8 Garde-fous récapitulés

1. Validation humaine obligatoire avant tout envoi, sur tous les canaux.
2. Email = seul canal envoyé de bout en bout par le système, plafonné par jour
   dans le code (5 par défaut : montée en charge douce d'un Gmail neuf).
3. Automatisation des plateformes en lecture seule + préremplissage ; le clic
   d'envoi est toujours humain.
4. Les candidatures ne peuvent affirmer que ce qui figure dans
   `config\profile.yaml` ou dans les CV (aucune invention possible).
5. Déduplication en base : jamais deux candidatures pour la même mission.
6. Secrets uniquement dans `.env` (jamais commité, jamais loggé).

---

## Annexe : arborescence

```
Prospector\
├── GUIDE.md              <- ce document
├── PLAN.md               <- plan d'implémentation détaillé
├── README.md             <- résumé setup + usage (anglais)
├── CLAUDE.md             <- règles d'or pour les agents Claude Code
├── config\               <- profile.yaml, targets.yaml, style.md
├── cv\                   <- sources HTML des 4 CV (fr/en x court/complet)
├── assets\cv\            <- les 4 PDF générés
├── data\
│   ├── prospector.db     <- SQLite (missions, candidatures, contacts, runs)
│   └── queue\            <- pending / approved / sent / rejected (fichiers .md)
├── scripts\              <- cœur déterministe Python (db, fetch, email, pdf...)
├── browser_profile\      <- sessions navigateur persistantes (créé au 1er login)
├── logs\                 <- digests quotidiens
└── .claude\              <- 7 agents + 5 skills
```
