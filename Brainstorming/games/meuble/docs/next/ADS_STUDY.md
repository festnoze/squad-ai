# Étude : quelle régie publicitaire pour Out of Sight (Android) ?

Date : 2026-11-24. Périmètre : jeu casual Unity 6.3, Android uniquement pour la pub, audience surtout France / UE,
formats plein écran (interstitiel, rewarded), pas de bannière. Recherche web volontairement courte (5 recherches, 3 pages
lues) : les chiffres ci-dessous sont des ordres de grandeur publics, pas des promesses.

## 1. Recommandation

**AppLovin MAX**, utilisé comme couche de médiation ("méta") : une seule intégration dans le jeu, et derrière elle on
active ou coupe des régies (AppLovin, Google AdMob en bidding, Unity Ads, Meta, Mintegral, ironSource Ads...) depuis le
tableau de bord MAX et l'Integration Manager, sans toucher au code. C'est le meilleur compromis pour "un seul fournisseur
maintenant, affiner plus tard".

Pourquoi :
- Leader du marché de la médiation (plus de 50 % de part de marché en 2025 ; MAX + LevelPlay + AdMob font plus de 90 %),
  et choix dominant du casual / hyper-casual, en partie parce qu'AppLovin est aussi un très gros annonceur de jeux.
- Sur les formats plein écran (rewarded, interstitiel), MAX et Unity Ads dépassent en général AdMob seul en eCPM sur
  les marchés Tier 1 pour les jeux Unity ; MAX a la plus forte profondeur d'enchères (RTB).
- La demande AppLovin n'est pleinement disponible que dans MAX : elle n'est pas bidder sur LevelPlay, et sur AdMob elle
  sous-performe et demande des montages hybrides.
- RGPD intégré : le flux "Terms and Privacy Policy" de MAX détecte les utilisateurs en zone RGPD et leur affiche Google
  UMP (la CMP certifiée Google, obligatoire pour servir la demande Google dans l'EEE), sans intégrer UMP à la main.
- Paiement à Net 15 (AdMob : Net 21).

Points de vigilance :
- Il faut aussi un compte AdMob (même compte Google que la Play Console) : pour le Google bidding dans MAX, et parce que
  le flux de consentement MAX affiche le message RGPD qu'on publie dans AdMob.
- Le marché bouge : fin 2025 / 2026, de gros éditeurs (Voodoo, Azur Games, Ubisoft, Fingersoft) sont passés à la
  médiation AdMob (Azur Games annonce +23 % d'ARPDAU). D'où l'architecture livrée : changer de régie = écrire un adaptateur
  et changer `provider` dans la config (voir docs/next/progress/ADSSHOP.md).
- L'adaptateur MAX a été écrit d'après la doc du plugin 8.x sans pouvoir être compilé (SDK non installé) : vérifier le
  premier build avec le symbole `OOS_ADS_APPLOVIN_MAX`.

**Plan B : Google AdMob + médiation AdMob.** Intégration la plus simple, UMP natif, la demande Google est la plus forte en
France, et on peut y ajouter AppLovin, Unity Ads, Meta en médiation. Choix raisonnable si le compte AppLovin pose problème.
Aucun adaptateur n'est écrit pour l'instant ; les ids de TEST officiels de Google sont déjà dans
`Assets/Resources/Config/ads.json` (bloc `admob`).

## 2. Comparatif

| Critère | AppLovin MAX | AdMob (+ médiation) | Unity LevelPlay (ironSource) | Unity Ads seul |
|---|---|---|---|---|
| Type | Médiation (bidding) | Régie + médiation (bidding + waterfall) | Médiation (passage au 100 % bidding) | Une seule régie |
| eCPM plein écran jeux | Le plus haut en Tier 1 | Correct, pas de benchmark publié | Bon, demande AppLovin absente | Bon sur les jeux Unity, mais une seule demande |
| Part de marché / dynamique | Plus de 50 %, leader | En forte reprise en 2026 | En recul, "exécute en silence" | Unity recommande lui-même LevelPlay |
| Intégration Unity | Package UPM + Integration Manager + EDM4U | Plugin Google Mobile Ads + UMP | Package "Ads Mediation" du registre Unity (le plus natif) | SDK Unity Ads (Unity recommande désormais de passer par LevelPlay) |
| RGPD / UMP | Flux intégré qui affiche UMP | UMP natif | À intégrer (UMP ou autre CMP) puis transmettre le consentement | À gérer soi-même |
| Paiement | Net 15 | Net 21 | Non vérifié dans cette étude | Non vérifié dans cette étude |

Une médiation bien réglée augmente typiquement l'eCPM de 30 à 100 % par rapport à une seule régie : c'est la raison
principale d'écarter "Unity Ads seul".

## 3. Ordres de grandeur d'eCPM (France / Europe, Android)

- Statista, France, juin 2023 : rewarded 4,69 $, interstitiel 3,14 $ (Android, in-app).
- Benchmarks 2025-2026 (Appodeal, Yodo1, Playio) : Europe Android de l'ordre de 5 $ en rewarded et 3,5 $ en
  interstitiel ; le rewarded reste le format le mieux payé, la bannière le moins bien. La France et l'Allemagne sont
  sous les meilleurs pays (US).
- Réalité d'un petit jeu indépendant : souvent en dessous (peu de volume, beaucoup de refus de consentement en UE).
  Exemple de calcul : 1 000 joueurs actifs par jour x 1,5 interstitiel par jour x 3 $ / 1 000 = environ 4,5 $ par jour.

## 4. Durée des pubs : ce qu'on contrôle vraiment

- **Côté code (client) : rien sur la durée.** Les SDK ne permettent pas de demander "une pub de 5 s" ou "de 15 s". On
  choisit quand afficher, quel format (interstitiel ou rewarded) et un nom de placement (pour les rapports).
- **Côté tableau de bord :**
  - AdMob : par bloc d'annonces interstitiel, on peut interdire la vidéo (images seulement, fermables tout de suite) ou
    couper les vidéos non désactivables (il ne reste que des vidéos qu'on peut passer après 5 s au plus). Les deux
    réduisent la demande, donc le revenu. Par défaut les deux types de vidéo sont autorisés.
  - MAX : pas de réglage de durée global ; certains réseaux proposent des options par placement dans leur propre
    tableau de bord. Les vidéos interstitielles du marché durent en général 15 à 30 s et deviennent fermables vers 5 s.
  - Rewarded : non passable par nature (sinon pas de récompense), et **obligatoirement opt-in** (politiques AdMob et
    AppLovin) : le joueur doit choisir de la regarder.
- **Dans notre config :** `preferredMaxDurationSeconds` (15) et `skippableAfterSeconds` (5) ne pilotent que le
  fournisseur "Simulated" (la fausse pub de développement). Pour la même raison, la pub automatique de fin de niveau est
  toujours un interstitiel avec une vraie régie, même si `format` vaut `rewarded` ; le rewarded reste disponible pour un
  futur bouton opt-in (`AdService.aShowRewardedAd`).

## 5. Fréquence retenue (valeurs par défaut de ads.json)

Inspirée des jeux casual qui marchent : jamais sur les premiers niveaux, jamais après un retry éclair, un cooldown.
- `firstEligibleLevel` 4 : les niveaux 1 à 3 (tutoriels, astuces) n'ont jamais de pub.
- `everyNLevelEnds` 2 : au plus une pub toutes les 2 fins de niveau éligibles.
- `minSecondsBetweenAds` 120 : 2 minutes minimum entre deux pubs.
- `minSecondsAfterLaunch` 90 : pas de pub dans la première minute et demie de session.
- `minSecondsInLevel` 20 : une partie de moins de 20 s (échec ou retry rapide) ne montre rien et ne compte pas.
- `placement` both : victoire et échec ; `showDelaySeconds` 1,2 : le panneau de résultat reste lisible avant la pub,
  et si le joueur a déjà tapé Rejouer ou Niveau suivant, la pub est annulée (elle n'interrompt jamais une partie).
- Jamais sur l'écran de fin du dernier niveau, jamais en mode spectateur, plus jamais une fois "Supprimer les pubs" acheté.

## 6. RGPD et consentement

- Utiliser le flux "Terms and Privacy Policy" de MAX (il affiche Google UMP aux utilisateurs RGPD au premier lancement).
- Prérequis : une politique de confidentialité en ligne (URL), et le message RGPD créé et **publié** dans AdMob
  (Confidentialité et messages).
- L'utilisateur doit pouvoir changer d'avis : la page Boutique affiche "Confidentialité des pubs" quand la régie le
  propose (MAX : utilisateur en zone RGPD), ce qui rouvre le formulaire (`MaxSdk.CmpService.ShowCmpForExistingUser`).
  Si un jour la boutique est masquée sur Android, il faudra placer ce bouton ailleurs (Options).
- Public cible Play Console : 13 ans et plus. Si une tranche "enfants" est cochée, le programme Familles impose des
  SDK publicitaires autocertifiés et des réglages spécifiques : vérifier la liste Google avant.

## 7. Mise en production pas à pas : pubs (AppLovin MAX)

Comptes et identifiants
1. Créer un compte AppLovin (dash.applovin.com), compléter paiement et fiscalité (formulaire W-8BEN pour un particulier
   résidant en France, W-8BEN-E pour une société).
2. Créer un compte AdMob (apps.admob.com) avec le compte Google de la Play Console ; y ajouter l'app Android
   (package `com.outofsight.game`) et noter l'**App ID AdMob** (`ca-app-pub-...~...`).
3. AdMob > Confidentialité et messages > RGPD : créer et publier le message de consentement (avec l'URL de la politique
   de confidentialité).
4. MAX > Account > General > Keys : noter la **SDK Key**.
5. MAX > Manage > Ad Units : créer un bloc **Interstitial** et un bloc **Rewarded** pour Android
   (`com.outofsight.game`) ; noter les deux **Ad Unit ID**.
6. MAX > Manage > Networks : activer Google bidding and Google AdMob (lier le compte AdMob), Unity Ads, et au choix
   Meta Audience Network, Mintegral, ironSource Ads, Liftoff, InMobi...

Unity
7. Télécharger le plugin MAX pour Unity (installeur `.unitypackage` de la page d'intégration Unity d'AppLovin) puis
   Assets > Import Package > Custom Package. Il ajoute le registre AppLovin et le package `com.applovin.mediation.ads`
   dans Packages/manifest.json, ainsi que l'External Dependency Manager (EDM4U).
8. AppLovin > Integration Manager : coller la SDK Key ; installer les adaptateurs des réseaux activés à l'étape 6 ;
   renseigner l'App ID AdMob Android dans la section Google.
9. Integration Manager > Privacy Settings : cocher "Enable MAX Terms and Privacy Policy Flow", renseigner Privacy Policy
   URL (obligatoire) et Terms of Service URL (optionnel). Pour tester depuis la France : "Debug User Geography" = GDPR
   (à remettre ensuite).
10. Assets > External Dependency Manager > Android Resolver > Settings : activer Jetifier, puis Resolve.
11. Project Settings > Player > Android > Other Settings > Scripting Define Symbols : ajouter `OOS_ADS_APPLOVIN_MAX`.
12. `Assets/Resources/Config/ads.json` : `"provider": "applovin_max"`, remplacer les deux `REPLACE_WITH_...` par les Ad
    Unit ID de l'étape 5 ; pour le premier test sur téléphone, `"showMediationDebugger": true` (puis `false`).
13. Compiler une fois : corriger d'éventuels écarts d'API dans `Assets/Scripts/Adapters/ApplovinMaxAdProvider.cs`.
14. Test : MAX > Test Mode, ajouter le téléphone (son identifiant publicitaire) ; vérifier dans le Mediation Debugger que
    les adaptateurs sont verts, puis jouer jusqu'au niveau 4 et au-delà.

Publication
15. Publier `app-ads.txt` à la racine du site du développeur (lignes fournies par AppLovin et AdMob) et renseigner ce
    site dans la fiche Play Store.
16. Play Console : déclarer "Contient des annonces", remplir la section Sécurité des données (identifiant publicitaire
    et données de diagnostic partagés avec les régies), public cible 13 ans et plus.
17. Google Play exige un AAB signé avec une vraie clé (le projet construit aujourd'hui un APK avec le keystore de debug) :
    créer un keystore de release et activer la génération d'AAB pour la publication.

## 8. Mise en production pas à pas : boutique (Unity IAP, Google Play Billing)

1. Play Console : activer le profil de paiement (compte marchand).
2. Envoyer un AAB signé (release) en test interne : Google ne laisse créer des produits qu'après un build contenant la
   permission de facturation (ajoutée par le package IAP).
3. Play Console > Monétiser > Produits > Produits intégrés : créer `no_ads`, `premium_pack`, `all_levels`, `tip_coffee`
   (identiques aux `storeId` de `Assets/Resources/Config/shop.json`), fixer les prix, activer.
4. Unity : Window > Package Manager > Unity Registry > In-App Purchasing (`com.unity.purchasing` 5.x) > Install.
5. Scripting Define Symbols : ajouter `OOS_IAP_UNITY`.
6. (Recommandé) Validation locale des reçus : Play Console > Monétiser > Configuration de la monétisation > clé de
   licence ; dans Unity, Services > In-App Purchasing > Receipt Validation Obfuscator (génère `GooglePlayTangle`) ; puis
   ajouter le symbole `OOS_IAP_RECEIPT_VALIDATION`.
7. `shop.json` : `"provider": "unity_iap"`.
8. Play Console > Paramètres > Test de licence : ajouter les comptes testeurs ; tester un achat, l'annulation, puis
   "Restaurer les achats" après réinstallation.
9. Compiler une fois : corriger d'éventuels écarts d'API dans `Assets/Scripts/Adapters/UnityIapStoreProvider.cs`.

## Sources

- [Nine facts about the mediation space in 2025 (PocketGamer.biz)](https://www.pocketgamer.biz/nine-facts-about-the-mediation-space-in-2025)
- [Mediations in 2025: 9 facts (Gamigion)](https://www.gamigion.com/mediations-in-2025-9-facts-out-there/)
- [Are ad mediation platform wars back in 2026? (Gamigion)](https://www.gamigion.com/are-ad-mediation-platform-wars-back-in-2026/)
- [AppLovin vs competitors (Playwire)](https://www.playwire.com/blog/choosing-your-platform-applovin-vs-competitors)
- [AdMob alternatives (Playwire)](https://www.playwire.com/blog/admob-alternatives-app-monetization-solutions-from-diy-to-fully-managed)
- [Best mobile ad networks 2025 (CAS.ai)](https://cas.ai/blog/the-best-mobile-ad-networks/)
- [AppLovin: The Apex Predator (Deconstructor of Fun)](https://www.deconstructoroffun.com/blog/2025/5/5/applovin-the-apex-predator)
- [eCPM par type d'annonce, France (Statista)](https://statista.com/statistics/1400838/ecpm-ad-type-ios-android-france)
- [Mobile game eCPM benchmarks 2025 (Yodo1)](https://www.yodo1.com/blog/mobile-game-ecpm-benchmarks-2025)
- [Mobile game eCPM benchmarks 2026 (Playio)](https://blog.playio.co/mobile-game-ecpm-benchmarks-2026)
- [Mobile eCPM report (Appodeal)](https://appodeal.com/blog/mobile-ecpm-report-app-ad-monetization-worldwide-performance)
- [Why Unity is moving to 100% in-app bidding (Unity)](https://unity.com/blog/unity-moving-to-in-app-bidding)
- [Migrate from Unity Ads to LevelPlay (Unity docs)](https://docs.unity.com/grow/levelplay/sdk/unity/migrate-from-unity-ads-to-levelplay)
- [MAX Unity integration (AppLovin)](https://support.applovin.com/en/max/unity/overview/integration)
- [MAX Unity interstitial ads (AppLovin)](https://support.applovin.com/en/max/unity/ad-formats/interstitial-ads)
- [MAX Unity Terms and Privacy Policy Flow (AppLovin)](https://support.applovin.com/en/max/unity/overview/terms-and-privacy-policy-flow)
- [AppLovin MAX Unity plugin (GitHub)](https://github.com/AppLovin/AppLovin-MAX-Unity-Plugin)
- [AdMob : vidéos dans les interstitiels (aide Google)](https://support.google.com/admob/answer/7311435?hl=en-GB)
- [AdMob : contrôler les vidéos interstitielles (aide Google)](https://support.google.com/admob/answer/9884467?hl=en)
