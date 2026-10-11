# Support client — spécification produit et technique

Version : 0.2, après critique croisée — 8 octobre 2026.

## 1. Objectif et contrat de génération

Construire **Relais Support**, application de support mono-organisation en français : tickets clients, traitement par l'équipe, échanges publics et notes internes. Benchmark Autospec borné, avec règles métier et conflits réalistes.

Stack : **Python/FastAPI, SQLite, React/TypeScript/Vite**. Monolithe, une origine HTTP, une image Docker. Étendre le socle Autospec, ses diagnostics et conventions de features ; ne pas recréer son bootstrap ou son câblage partagé sans nécessité.

Ce brief et [le référentiel indépendant](02_requirements_verification.md) forment le contrat. Le constructeur ne modifie pas les exigences pour obtenir du vert. Toute contradiction exige un arbitrage. Charger les deux documents pour construire ; importer ce brief dans Autospec, conserver le référentiel comme annexe de test.

Hypothèses : données fictives, loopback, petite équipe, une instance et SQLite. Pas de mise en production publique, dépense, email ou système externe.

### Périmètre fermé

Inclus : sessions, trois rôles, comptes, tickets/priorité/affectation/workflow, conversations, historique, recherche/filtres/pagination, compteurs, tests et Docker persistant.

Exclus : inscription publique, récupération de mot de passe, MFA/SSO, pièces jointes, texte enrichi, suppression physique, multi-tenant, SLA, notifications, WebSocket, IA, CSV, tags et automatisations. Ne pas ajouter ces fonctions. Rôle et email immuables après création.

## 2. Acteurs et autorisations

Un compte possède exactement un rôle : `client`, `agent` ou `admin`. `admin` inclut les droits d'agent. Un compte désactivé ne peut plus effectuer aucune opération authentifiée, même avec une session antérieure.

| Opération | Client | Agent | Admin |
|---|---|---|---|
| Créer un ticket | Oui, pour soi | Non | Non |
| Lister/lire des tickets | Les siens uniquement | Tous | Tous |
| Modifier le titre/la description | Non après création | Non | Non |
| Publier une réponse | Sur ses tickets non fermés | Sur tout ticket non fermé | Idem agent |
| Lire/écrire une note interne | Jamais | Tout ticket non fermé ; lecture aussi après fermeture | Idem agent |
| Modifier priorité/affectation/statut | Non | Oui selon règles ci-dessous | Idem agent |
| Voir les indicateurs | Ses tickets uniquement | Tous | Tous |
| Lister/créer/activer/désactiver des comptes | Non | Non | Oui |

Le serveur contrôle chaque route/objet : ticket d'autrui ou absent => `404` identique ; capacité interdite => `403` ; anonyme sur API métier => `401`. Les notes internes et leurs événements sont exclus des DTO clients **avant** pagination et calcul des totaux. L'annuaire personnel expose seulement IDs/noms des agents/admins actifs. Pas d'emails de clients via cet annuaire.

Confidentialité retenue : aucun contenu, auteur ou compteur de notes internes exposé. L'évolution de `version`/`updated_at` du ticket reste visible à tous ses lecteurs ; masquer toute existence d'activité interne est hors périmètre. Les compteurs du dashboard comptent les tickets, jamais les notes.

L'autorisation sur chaque objet est notamment destinée à prévenir les accès directs par identifiant ; des UUID seuls ne constituent pas cette protection. [Principe OWASP BOLA](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)

## 3. Comptes, authentification et initialisation

### Règles des comptes

- Email : retirer les espaces périphériques et passer en minuscules avant contrôle ; unicité en base sur cette valeur, y compris pour un compte désactivé. Format valide, longueur maximale 254.
- Nom d'affichage : 1 à 80 caractères après retrait des espaces périphériques.
- Mot de passe : 14 à 128 caractères ; espaces et Unicode acceptés ; ne jamais le tronquer ni le normaliser silencieusement. Hachage Argon2id par une bibliothèque maintenue, sel par mot de passe ; ni clair, ni chiffrement réversible. Minimum du profil retenu : mémoire 19 Mio, 2 itérations, parallélisme 1. [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- Création de compte par un admin avec rôle explicite, nom, email et mot de passe initial saisi. Aucun mot de passe n'est renvoyé dans les DTO de compte. Pas de changement de mot de passe dans ce benchmark local ; cela reste un prérequis avant un usage réel.
- Désactiver le dernier admin actif => `409`, y compris en concurrence ; contrôle et écriture atomiques. Invalider définitivement toutes les sessions du compte : sa réactivation ne les restaure pas.
- Désactivation d'un agent/admin : tous ses tickets, **même fermés**, deviennent non affectés dans la transaction ; version et historique de chaque ticket changent. Exception système à l'interdiction d'affecter un ticket fermé. Comptes, tickets et messages ne sont pas supprimés.

### Sessions

Session serveur opaque : jeton cryptographiquement aléatoire d'au moins 256 bits, condensat en DB ; cookie `HttpOnly`, `SameSite=Lax`, `Path=/`. Expiration absolue à 8 h, jeton neuf à chaque login, compte actif vérifié par requête. Aucun secret de session dans localStorage/URL/logs. [OWASP Sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

`Secure=true` en configuration HTTPS ; exception explicite uniquement pour le développement HTTP loopback. Les routes métier ne deviennent pas publiques dans cette exception. Les données privées et réponses d'authentification portent `Cache-Control: no-store`.

Mutations : `Origin` obligatoire et égal à l'origine configurée (absent/`null`/étranger refusés), login/logout compris ; CORS sans wildcard credentials. Session authentifiée : exiger aussi `X-CSRF-Token` lié à celle-ci. Token fourni par login ou `/auth/me`, gardé en mémoire. Login sans CSRF préalable. Logout avec session valide exige CSRF, révoque la session et expire le cookie ; sans session valide, il expire le cookie et renvoie `204` (exception idempotente au `401`). Sur API métier, l'absence de session donne `401` avant contrôle CSRF. [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

Échecs login : même `401`/message pour email absent, mot de passe faux, compte inactif. Vérification de hash factice si compte absent. Dix échecs/IP dans une fenêtre de 60 s depuis le premier échec ; tentative suivante => `429`/`Retry-After`. Succès ne remet pas ce compteur à zéro. Mémoire acceptée en mono-instance ; ignorer X-Forwarded-For sans proxy de confiance. Horloge injectable.

### Premier démarrage et fixtures

Commandes distinctes : premier admin par saisie interactive (refuser si un admin existe) ; fixtures via `--demo` explicite. Aucun compte par défaut. Credentials fournis au harnais par environnement/saisie, jamais codés en dur, copiés dans l'image ou journalisés. Seed sans credentials => échec ; rejeu idempotent, sans effacement ni remise à zéro de mots de passe ; conflit avec des données préexistantes => refus explicite.

Fixture : exactement cinq comptes, clients Alice/Bob, agents Camille/Dylan, admin Emma ; 12 tickets, 6/client, quatre statuts, trois priorités, affectés/non affectés et conversation mixte publique/interne. IDs/dates fixes ; manifest avec propriétaire, statut, priorité, assigné et compteurs attendus. Prévoir Alice-open non assigné, Alice-in_progress assigné avec échanges mixtes, Bob-resolved assigné avec réponse publique, Bob-closed assigné. Tester le bootstrap admin sur une autre base vierge. Pas de réinitialisation automatique du service livré.

## 4. Tickets et cycle de traitement

Un ticket contient : identifiant stable, titre, description initiale, propriétaire immuable, statut, priorité, éventuel agent affecté, date de création, date de dernière modification et entier `version`.

- Création : titre 5–120 caractères ; description 20–5 000 ; validation après retrait des espaces périphériques, contenu uniquement blanc refusé. Statut `open`, priorité `normal`, affectation vide et version 1 imposés par le serveur. Le propriétaire vient de la session, jamais d'un champ client.
- Priorités : `low`, `normal`, `high`. Modifiables par agent/admin, y compris sur un ticket fermé.
- Affectation : uniquement un agent/admin actif, ou `null` ; changement interdit si état initial ou résultant `closed`. Un ticket non affecté reste visible à tous les agents. Une désactivation concurrente ne peut pas laisser une affectation vers un compte inactif.
- Aucune suppression de ticket. Titre, description, propriétaire et date initiale ne sont plus modifiables après création.

### Transitions autorisées

| Depuis | Vers | Condition |
|---|---|---|
| `open` | `in_progress` | Agent actif affecté |
| `in_progress` | `open` | Aucune condition supplémentaire |
| `in_progress` | `resolved` | Au moins une réponse publique d'un agent/admin existe |
| `resolved` | `in_progress` | Agent actif affecté ; réouverture |
| `resolved` | `closed` | Aucune condition supplémentaire |

Autres changements de statut => `409`, sans écriture ; statut identique => no-op autorisé. `closed` terminal. Aucun message ne change implicitement le statut. Un agent non assigné peut répondre. Désaffecter un ticket `in_progress` conserve ce statut ; il apparaît dans « non affectés ». La précondition d'assignation s'applique aux transitions vers `in_progress`, pas au maintien de cet état.

### Concurrence et opérations atomiques

PATCH ticket : `expected_version` obligatoire et au moins un champ statut/priorité/assignation. Valider l'état résultant, écrire ticket + historique atomiquement ; un incrément de version par mutation effective. No-op => `200` sans événement/incrément. Version obsolète => `409 VERSION_CONFLICT`, **même pour un no-op** ; UI proposant de recharger en conservant le brouillon, jamais de réapplication automatique.

Deux mutations effectives concurrentes de même version : une réussite, un `409`. Course fermeture/message : fermeture gagnante => message refusé ; message gagnant => version changée et fermeture obsolète refusée. Refus métier, panne DB ou conflit : aucune écriture partielle ni événement orphelin. Un contrôle « lire puis écrire » sans transaction/CAS est insuffisant.

## 5. Conversations et historique

Message : auteur/date UTC serveur, contenu texte 1–5 000 caractères après trim, visibilité public/internal. Ni édition ni suppression. Client tentant internal => `403`. Ticket fermé => aucun **nouveau** message/note (`409`). Auteur/rôle/date du payload interdits.

Création ticket/message : `client_request_id` UUID neuf par soumission, conservé en mémoire pour les retries **sans recharger la page**. Déduplication durable par utilisateur + type d'opération + UUID. Comparer payload normalisé, visibilité et **ticket cible** : identique => même objet (`200`, première fois `201`) ; différent => `409 IDEMPOTENCY_CONFLICT`. Clé/objet/événement atomiques et persistants après redémarrage serveur. Nouveau brouillon => nouvelle clé ; pas de retry automatique après rechargement navigateur.

Replay : authentification et droits actuels d'abord, puis déduplication. Un message déjà créé est rejouable même si le ticket est désormais fermé ; ce n'est pas une nouvelle écriture. Une nouvelle clé reste refusée sur fermé. Après timeout, réessayer le même payload/UUID avant toute édition : modifier un résultat incertain ne doit pas créer un doublon.

Les messages apparaissent dans l'ordre `(created_at, id)` croissant. Une note interne possède un libellé explicite et un style distinct, pas seulement une couleur. Le ticket prend une nouvelle version pour chaque message effectif, y compris une note interne ; le client ne reçoit aucun contenu interne.

Historique append-only : acteur, type, date, changements avant/après. Création et mutation ticket/message avec audit atomique. Événement de message : ID/visibilité seulement, pas de copie du corps. Le client voit les événements publics ; les notes internes/événements associés restent réservés à l'équipe.

Tous les textes métier sont rendus comme du texte : une chaîne `<script>` ou `<img onerror=...>` reste inerte. Aucune utilisation de rendu HTML brut pour les données utilisateur.

## 6. Recherche, indicateurs et expérience utilisateur

### Liste des tickets

Recherche sur titre/description uniquement ; `q` 0–100 caractères. Casse insensible pour ASCII ; Unicode conservé et cherchable à l'identique, sans promesse d'équivalence accentuée. `%`, `_` et apostrophes sont littéraux. Filtres/recherche serveur dans le périmètre autorisé, avant pagination.

Filtres ET : statut, priorité, affecté à moi, non affectés. Deux derniers réservés au personnel et exclusifs (`422` si cumul). Tri `(updated_at DESC,id DESC)`. `page>=1`, `page_size=1..50` (défaut 20), réponse `{items,total,page,page_size}`. Total avec mêmes filtres/droits ; page trop haute vide. Jeu stable : aucun doublon/oubli ; pas de snapshot garanti entre pages si mutations concurrentes.

### Cinq vues maximum

1. Connexion : labels visibles, erreur claire, bouton indisponible pendant la requête.
2. Mes tickets/file d'équipe : filtres, tableau ou cartes lisibles, pagination, création client dans une modale ou un panneau.
3. Détail : titre/contenu, statut/priorité/assignation, fil de messages, historique et zone de réponse. L'onglet note interne n'existe pas côté client.
4. Tableau de bord : nombre total et quatre compteurs par statut, dans le périmètre du rôle ; pas de graphique complexe ni de moteur analytique. Mise à jour après mutation et au rechargement.
5. Administration des comptes : liste paginée, création, activation/désactivation et confirmation avant désactivation. Pas de modification du rôle/email.

Chaque vue : chargement, vide, erreur récupérable et succès distincts. Erreurs persistantes/contextuelles. Brouillon conservé après refus/conflit/panne réseau, effacé au logout/expiration. Bouton désactivé pendant envoi, sans remplacer l'idempotence serveur. Timeout HTTP frontend de 15 s maximum avec reprise explicite.

Filtres/page dans l'URL ; filtre changé => page 1. Une ancienne réponse réseau ne remplace pas la recherche courante. `401` : vider l'état privé et revenir au login. `403/404` : effacer l'ancienne fiche et afficher le refus. Changement de compte : aucun cache privé précédent réexposé.

Clavier, focus visible, labels/erreurs liés aux champs, tabulation logique ; modale avec focus confiné, Échap et retour au déclencheur. Statuts non fondés seulement sur la couleur. Bureau 1280 px et mobile 390 px sans débordement global. Pas de pixel-perfect ni bibliothèque UI imposée.

## 7. Contrat API et données

Préfixe métier `/api`. Routes minimales ; les variantes non listées ne sont pas nécessaires :

| Routes | Contrat principal |
|---|---|
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Connexion, invalidation, identité/CSRF ; `/me` non connecté => 401 |
| `GET/POST /users`, `PATCH /users/{id}` | Admin seulement ; PATCH accepte uniquement `active` |
| `GET /assignees` | Agent/admin ; annuaire minimal des assignables actifs |
| `GET/POST /tickets`, `GET/PATCH /tickets/{id}` | Périmètre et versions définis ci-dessus |
| `GET/POST /tickets/{id}/messages` | Pagination serveur et filtrage de visibilité |
| `GET /tickets/{id}/history` | Pagination serveur et filtrage de visibilité |
| `GET /dashboard` | `{total, by_status:{open,in_progress,resolved,closed}}` |

Toutes les listes sont paginées, annuaire compris. Comptes/annuaire : `(email_normalized ASC,id ASC)` ; messages/historique : `(created_at ASC,id ASC)`. Détail sans collections non bornées. IDs UUID, séquence interne d'historique admise. Payloads stricts : champs inconnus/interdits => `422`.

Lecture/PATCH : 200 ; création : 201 ; logout : 204. Erreurs JSON `{error:{code,message,fields?}}`, codes stables/message français : 422 validation, 401 session, 403 capacité/CSRF/origine, 404 ticket absent/invisible, 409 invariant/version/doublon, 429 login. Verrou SQLite : attente maximale 5 s puis 503 `DB_BUSY`, aucun faux succès. Pas de stacktrace/SQL/secret dans les erreurs.

Entités : users, sessions, tickets, messages, ticket_events, clés d'idempotence (table/colonnes dédiées). FK actives par connexion ; unicité, NOT NULL, domaines/versions protégés ; index justifiés pour listes et conversations. Pas de blob JSON remplaçant une entité. Transactions courtes, sans appel réseau ; protection valable sur connexions DB distinctes.

Dates UTC, ISO8601 avec fuseau ; affichage local. Migration initiale versionnée/rejouable sans perte de données. Heure injectable. Requêtes paramétrées, jamais de concaténation SQL d'entrée utilisateur.

## 8. Organisation du code et livraison

Backend : routeurs/schémas, services, accès DB et configuration séparés ; permissions/invariants centralisés. SQLAlchemy ou sqlite3 acceptés avec garanties équivalentes. Pas de couches génériques sans besoin.

Frontend par domaines auth/tickets/users ; client HTTP commun pour cookies/CSRF/erreurs/annulation ; formulaires/DTO typés. Présentation séparée de l'état serveur et des permissions. Ni fichier géant ni gestionnaire d'état supplémentaire imposé.

Conserver diagnostics du socle, dont `/api/health` et DB : publics, sans données privées. UI/API réelles, SQLite sur volume, non-root, loopback, locks, aucune installation au runtime. Exclure secrets, DB locales et dossiers de développement de l'image.

README : prérequis/configuration, bootstrap/seed/migrations, tests/build/Docker, persistance/retrait/nettoyage explicite, limites locales. Tests sur base temporaire. Audit daté des dépendances : aucun défaut critique/élevé exploitable non arbitré ; audit indisponible signalé, jamais déclaré vert.

## 9. Lots et définition de terminé

**7 lots maximum**, chacun testé : (1) DB/migration/healthcheck ; (2) login/logout UI+API ; (3) créer/lire un ticket UI+API ; (4) workflow/affectation/conversations ; (5) administration ; (6) filtres/dashboard/états UX ; (7) négatifs/concurrence/E2E/Docker/docs. Les tests accompagnent chaque lot, pas uniquement le dernier. Éviter micro-stories et design prolongé. Pas de coût/délai de génération garanti avant mesure.

Terminé : trois rôles opérationnels, exigences du référentiel satisfaites, tests reproductibles et parcours sur image finale avec persistance après recréation. Ni UI mockée, ni healthcheck ou taux de couverture seul ne suffit.

Cibles après installation : tests hors navigateur <2 min, six parcours E2E <3 min sur machine documentée ; diagnostics, pas seuils éliminatoires. Couverture : backend ≥80% lignes/70% branches, frontend ≥70% lignes métier, fichiers non exécutés inclus, exclusions justifiées. Mapping requirements → tests explicite. Matrices API paramétrées ; pas toute la combinatoire en navigateur.

## 10. Journal de critique et de refinement

v0.1 : première rédaction. v0.2 : deux revues indépendantes, sécurité/intégrité et périmètre/UX, puis arbitrages : no-op distingués des transitions ; replay lié à la cible et autorisé après fermeture ; sessions révoquées définitivement ; exceptions logout/désaffectation précisées ; métadonnées internes explicitement admises ; course fermeture/message couverte ; fixtures isolées ; première tranche UI dès les lots 2–3. Contrats courts pour limites, pagination, erreurs et couverture. Brief compacté sous les 20 000 caractères de l'import Autospec. Pas d'extension aux fonctions exclues.
