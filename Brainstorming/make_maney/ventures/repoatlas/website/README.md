# RepoAtlas website

B2B marketing site for the RepoAtlas platform (see ../PLATFORM.md). Static,
zero build: open `index.html` in a browser, or serve the folder with
`python -m http.server 8096`.

Pages:
- `index.html` - problem, the 5-stage recovery path, the 7 offerings as a
  map legend, proof/guarantees, audiences, FAQ
- `offerings.html` - one detailed section per offering with a price card
- `method.html` - the fact graph, the six delivery gates, engagement flow,
  security posture

Design language: surveying/cartography (the brand is an atlas). Chart-navy
ink on cool paper, survey-marker orange, contour-line hero map, evidence
tags in mono. Fonts via Google Fonts (Bricolage Grotesque / Public Sans /
IBM Plex Mono) with graceful system fallbacks.

Before going live:
- Replace `hello@repoatlas.dev` with the real address once the domain is
  chosen and verified (candidates in ../PRD.md section 2).
- Add legal pages (mentions legales / privacy) required for an FR/EU site.
- Plug a real booking link (Cal.com or similar) in place of the mailto CTAs.
- Publish the two sample Atlas Packs and link them from the hero
  ("see a real pack" is the strongest proof this page can offer).
