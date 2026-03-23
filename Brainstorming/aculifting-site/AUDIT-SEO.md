# Audit SEO - Site Aculifting Yamina Heinrich

> Audit realise le 23/03/2026 sur les fichiers `site.html` et `wip.html`

---

## Resume executif

| Categorie | Score | Priorite |
|---|---|---|
| Contenu rendu JS (critique) | :red_circle: | P0 |
| Meta tags & mots-cles | :orange_circle: | P1 |
| Donnees structurees (Schema.org) | :orange_circle: | P1 |
| SEO local (Montpellier) | :red_circle: | P1 |
| Open Graph / reseaux sociaux | :orange_circle: | P2 |
| Performance & technique | :orange_circle: | P2 |
| Accessibilite & semantique HTML | :yellow_circle: | P2 |
| Fichiers techniques (robots, sitemap...) | :red_circle: | P1 |
| Images & medias | :orange_circle: | P3 |
| Page WIP (en construction) | :yellow_circle: | P3 |

---

## P0 - CRITIQUE : Contenu rendu cote client (JavaScript)

### Probleme

Le contenu principal du site (titres h1/h2, paragraphes, navigation, benefices) est **genere dynamiquement par JavaScript** via l'objet `SITE_CONFIG`. Le HTML source contient des balises vides :

```html
<h1 class="hero-title" id="heroTitle"></h1>
<p class="hero-tagline" id="heroTagline"></p>
<h2 id="aboutTitle"></h2>
```

Google peut executer le JS, mais :
- L'indexation est **retardee** (file d'attente de rendu, parfois plusieurs jours)
- Le contenu genere par JS est considere comme **moins fiable** par les crawlers
- Bing, Yandex, et la plupart des reseaux sociaux **ne rendent pas le JS**
- Les extraits enrichis (featured snippets) privilegient le HTML statique

### Solution recommandee

**Passer tout le contenu textuel en HTML statique dans le fichier `site.html`.**
Garder le JS uniquement pour les interactions (menu mobile, scroll, FAQ accordion, animations).

Concretement :
- [ ] Ecrire directement le nom, titres, paragraphes dans le HTML
- [ ] Supprimer l'objet `SITE_CONFIG` ou le reduire aux seules donnees dynamiques
- [ ] Garder les `id` pour le JS interactif, mais pre-remplir le contenu

---

## P1 - Meta tags & mots-cles

### Etat actuel (`site.html`)

```html
<meta name="keywords" content="aculifting, acupuncture esthétique, lifting naturel, rajeunissement visage, techniques non invasives">
<meta name="description" content="Yamina Heinrich, spécialiste en Aculifting. Techniques esthétiques non invasives pour redonner éclat et jeunesse à votre visage naturellement.">
<title>Yamina Heinrich - Spécialiste en Aculifting | Techniques esthétiques non invasives</title>
```

### Problemes identifies

1. **Mots-cles manquants** : des termes de recherche courants sont absents
2. **Pas de localisation** dans la meta description ni le title (Montpellier)
3. **Meta description** trop generique, pas assez incitative (manque de CTA)
4. **Title** un peu long (72 caracteres, ideal < 60)

### Corrections recommandees

**Meta keywords** (meme si Google les ignore, Bing et d'autres les lisent) :
```html
<meta name="keywords" content="aculifting, aculifting montpellier, acupuncture esthetique, acupuncture visage, lifting naturel, rajeunissement visage, soin visage naturel, medecine traditionnelle chinoise, anti-age naturel, rides, collagene, beaute naturelle, soin non invasif, acupuncture montpellier, lifting sans chirurgie">
```

**Meta description** (150-160 caracteres, avec CTA et localisation) :
```html
<meta name="description" content="Yamina Heinrich, specialiste en Aculifting a Montpellier. Soin du visage naturel et non invasif : reduction des rides, eclat du teint. Prenez rendez-vous.">
```

**Title** (< 60 caracteres) :
```html
<title>Aculifting Montpellier | Yamina Heinrich - Soin visage naturel</title>
```

---

## P1 - Donnees structurees (Schema.org / JSON-LD)

### Etat actuel

```json
{
  "@type": "MedicalBusiness",
  "name": "Yamina Heinrich - Aculifting",
  "description": "...",
  "telephone": "+33613238681",
  "email": "aculifting.mtc@gmail.com",
  "address": {
    "streetAddress": "622 avenue Xavier de Ricard",
    "addressLocality": "France"    // <-- ERREUR
  }
}
```

### Problemes

- `addressLocality` devrait etre `"Montpellier"`, pas `"France"` (France = `addressCountry`)
- Manque : `postalCode`, `addressRegion`, `addressCountry`
- Manque : `geo` (coordonnees GPS) pour Google Maps
- Manque : `openingHoursSpecification` (horaires)
- Manque : `priceRange` (fourchette de prix)
- Manque : `image`, `url`, `sameAs` (reseaux sociaux)
- **Pas de schema FAQPage** pour la section FAQ (opportunite de rich snippets)

### Schema.org corrige et enrichi

```json
{
  "@context": "https://schema.org",
  "@type": "HealthAndBeautyBusiness",
  "name": "Yamina Heinrich - Aculifting",
  "description": "Specialiste en Aculifting a Montpellier. Techniques esthetiques non invasives pour le rajeunissement naturel du visage.",
  "url": "https://www.URL-DU-SITE.fr",
  "telephone": "+33613238681",
  "email": "aculifting.mtc@gmail.com",
  "image": "https://www.URL-DU-SITE.fr/photo-yamina-heinrich.jpg",
  "priceRange": "$$",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "622 avenue Xavier de Ricard",
    "addressLocality": "Montpellier",
    "postalCode": "34000",
    "addressRegion": "Occitanie",
    "addressCountry": "FR"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": 43.6112,
    "longitude": 3.8767
  },
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday"],
      "opens": "09:00",
      "closes": "18:00"
    }
  ],
  "sameAs": [
    "https://www.instagram.com/PROFIL_REEL",
    "https://www.facebook.com/PROFIL_REEL"
  ]
}
```

### Ajouter un schema FAQPage (rich snippets Google)

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "L'aculifting est-il douloureux ?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Non, l'aculifting est indolore..."
      }
    }
  ]
}
```

Cela permet d'obtenir des **accordeons directement dans les resultats Google**.

---

## P1 - SEO local (Montpellier)

### Problemes

Le mot **"Montpellier"** n'apparait quasiment nulle part dans le contenu indexable :
- Absent du `<title>`
- Absent de la `<meta description>`
- Absent du `<h1>` et des `<h2>`
- Present uniquement dans l'adresse de la section contact (qui est rendue en JS)

### Actions recommandees

- [ ] **Title** : inclure "Montpellier" → `Aculifting Montpellier | Yamina Heinrich`
- [ ] **Meta description** : inclure "a Montpellier"
- [ ] **H1 ou sous-titre** : mentionner "Montpellier" dans le hero ou le about
- [ ] **Contenu** : ajouter une phrase du type _"Je vous accueille dans mon cabinet au quartier Les Aubes a Montpellier"_
- [ ] **Schema.org** : corriger `addressLocality` (voir section precedente)
- [ ] **Google Business Profile** : creer une fiche Google My Business (essentiel pour le SEO local) et lier le site
- [ ] **Nom de domaine** : envisager un domaine incluant "montpellier" ou "aculifting" si possible

---

## P2 - Open Graph & reseaux sociaux

### Etat actuel

```html
<meta property="og:title" content="Yamina Heinrich - Spécialiste en Aculifting">
<meta property="og:description" content="Redonnez éclat...">
<meta property="og:type" content="website">
<meta property="og:locale" content="fr_FR">
```

### Manquant

- [ ] `og:image` (image de partage, idealement 1200x630px) - **indispensable** pour les partages Facebook/LinkedIn
- [ ] `og:url` (URL canonique)
- [ ] `og:site_name`
- [ ] **Twitter Card** absentes :

```html
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Aculifting Montpellier | Yamina Heinrich">
<meta name="twitter:description" content="Soin du visage naturel et non invasif a Montpellier">
<meta name="twitter:image" content="https://www.URL-DU-SITE.fr/og-image.jpg">
```

---

## P2 - Performance & technique

### Problemes identifies

1. **3 polices Google Fonts chargees** (Playfair Display, Cormorant Garamond, Lato) avec de nombreuses variantes de poids
   - Impact : 200-400ms de temps de chargement supplementaire
   - Solution : ajouter `&display=swap` (deja present) mais envisager de reduire les variantes

2. **Pas de favicon** declare
   - Ajouter : `<link rel="icon" href="favicon.ico">`
   - Creer aussi un `apple-touch-icon` pour iOS

3. **Pas de `<link rel="canonical">`**
   - Risque de contenu duplique si le site est accessible via plusieurs URLs
   - Ajouter : `<link rel="canonical" href="https://www.URL-DU-SITE.fr/">`

4. **Iframe Google Maps** sans title
   - Ajouter un attribut `title="Localisation du cabinet Yamina Heinrich a Montpellier"` pour l'accessibilite

5. **Nom de fichier image avec espaces** : `image carte visite transparente.svg`
   - Renommer en `logo-yamina-heinrich-aculifting.svg` (plus descriptif, sans espaces, mots-cles)

---

## P1 - Fichiers techniques manquants

### robots.txt

Creer un fichier `robots.txt` a la racine :

```
User-agent: *
Allow: /

Sitemap: https://www.URL-DU-SITE.fr/sitemap.xml
```

### sitemap.xml

Creer un fichier `sitemap.xml` :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.URL-DU-SITE.fr/</loc>
    <lastmod>2026-03-23</lastmod>
    <priority>1.0</priority>
  </url>
</urlset>
```

### Lien canonique

```html
<link rel="canonical" href="https://www.URL-DU-SITE.fr/">
```

---

## P2 - Accessibilite & semantique HTML

### Problemes

1. **Pas de balise `<main>`** englobant le contenu principal
2. **Pas de balise `<header>`** pour la navigation (utilise `<nav>` directement, c'est OK mais `<header>` est preferable en parent)
3. **Attribut `aria-label`** de la navigation en anglais ("Toggle navigation") → Mettre en francais
4. **Liens sociaux generiques** (`https://www.instagram.com`, `https://www.facebook.com`) → Lier aux vrais profils ou supprimer
5. **Formulaire desactive** sans explication visible pour l'utilisateur → Expliquer ou supprimer
6. **Lien "Contact" en double** dans le footer (lignes 439-440 de site.html)
7. **Attribut `lang="fr"`** est present

---

## P3 - Images & medias

### Problemes

1. **Aucune vraie photo** sur le site (placeholder SVG "Photo professionnelle de Yamina Heinrich")
   - Google Images est une source importante de trafic local
   - Ajouter : photo pro du praticien, photos du cabinet, photos avant/apres (si autorise)

2. **Nom du fichier logo** non optimise (`image carte visite transparente.svg`)
   - Renommer : `logo-yamina-heinrich-aculifting.svg`

3. **Alt text du logo** correct mais repetitif sur 2 occurrences

4. **Pas d'image OG** pour le partage social (voir section Open Graph)

### Actions recommandees

- [ ] Ajouter au minimum 3-5 photos reelles optimisees (compressees, nommees avec mots-cles)
- [ ] Nommer les images de facon descriptive : `soin-aculifting-montpellier.jpg`, `cabinet-aculifting-yamina-heinrich.jpg`
- [ ] Ajouter des alt text descriptifs incluant les mots-cles
- [ ] Creer une image OG de partage (1200x630px)

---

## P3 - Page WIP (`wip.html`)

La page "en construction" a aussi besoin d'un minimum de SEO car c'est elle qui est indexee actuellement.

### Manquant sur wip.html

- [ ] `<meta name="keywords">` absent
- [ ] Open Graph absent (si partage du lien)
- [ ] Schema.org absent (au minimum les coordonnees)
- [ ] Pas de `canonical`

### Ajouts recommandes pour wip.html

```html
<meta name="keywords" content="aculifting montpellier, yamina heinrich, acupuncture esthetique montpellier, soin visage naturel">

<meta property="og:title" content="Yamina Heinrich - Aculifting Montpellier">
<meta property="og:description" content="Site en construction. Contactez Yamina Heinrich pour un soin Aculifting a Montpellier.">
<meta property="og:type" content="website">
<meta property="og:locale" content="fr_FR">
```

---

## Checklist de mots-cles recommandes

Voici les mots-cles a integrer dans les meta, titres, et contenu du site :

### Mots-cles principaux
- aculifting
- aculifting montpellier
- acupuncture esthetique
- lifting naturel

### Mots-cles secondaires
- acupuncture visage
- soin visage naturel
- rajeunissement visage
- anti-age naturel
- medecine traditionnelle chinoise
- beaute naturelle
- rides naturel
- collagene naturel

### Mots-cles longue traine (opportunites)
- aculifting prix montpellier
- acupuncture esthetique visage montpellier
- alternative naturelle botox
- lifting sans chirurgie montpellier
- soin anti-rides naturel montpellier
- acupuncture rides visage

### Mots-cles locaux
- montpellier
- les aubes montpellier
- herault
- occitanie

---

## Plan d'action par priorite

### Immediat (P0)
1. Passer le contenu de `SITE_CONFIG` en HTML statique

### Court terme (P1)
2. Corriger et enrichir les meta tags (title, description, keywords)
3. Corriger et completer le Schema.org JSON-LD
4. Ajouter le schema FAQPage
5. Integrer "Montpellier" dans le contenu visible
6. Creer robots.txt et sitemap.xml
7. Ajouter `<link rel="canonical">`

### Moyen terme (P2)
8. Completer les meta Open Graph (ajouter og:image)
9. Ajouter les Twitter Cards
10. Ajouter des vraies photos (praticien, cabinet)
11. Renommer le fichier logo
12. Ajouter un favicon
13. Corriger les problemes d'accessibilite
14. Creer une fiche Google Business Profile

### Bonus (P3)
15. Optimiser les meta de wip.html
16. Ajouter des temoignages avec schema Review
17. Creer un blog/articles pour le content marketing (ex: "Qu'est-ce que l'aculifting ?")
18. Inscrire le site dans des annuaires locaux (PagesJaunes, Doctolib, etc.)
