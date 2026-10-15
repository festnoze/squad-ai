from pathlib import Path
from html import escape, unescape
import json, re
ROOT=Path(__file__).resolve().parent
cv=json.loads((ROOT/'data/resume.json').read_text(encoding='utf-8'))
def plain(value):return unescape(re.sub(r'<[^>]+>',' ',value or '')).strip()
def e(value):return escape(str(value or ''),quote=True)
def rich(value):return value or ''
def arrow():return '<span aria-hidden="true">↗</span>'
name=cv['name']['firstName']+' '+cv['name']['lastName'].title()
email=next(c['value'] for c in cv['contact']['items'] if 'envelope' in c['icon'])
linkedin=next(c['href'] for c in cv['contact']['items'] if 'linkedin' in c['icon'])
phone=next(c['value'] for c in cv['contact']['items'] if 'phone' in c['icon'])
# Preserve every skill and original description.
skill_groups=[]
for s in cv['skills']:
    if 'group' in s:skill_groups.append({'name':s['group'],'items':[]})
    else:skill_groups[-1]['items'].append(s)
expertise=''
for i,g in enumerate(skill_groups):
    items=''.join(f'<li><h4>{rich(s["title"])}</h4><p>{rich(s["desc"])}</p></li>' for s in g['items'])
    labels=['Intelligence artificielle','Ingénierie logicielle','Leadership & méthodes']
    expertise+=f'<article class="expertise-panel reveal"><div class="panel-index"><span>0{i+1}</span><span class="panel-mark" aria-hidden="true">{["✳","⌘","↗"][i]}</span></div><p class="eyebrow">{rich(g["name"])}</p><h3>{labels[i]}</h3><ul class="skill-list">{items}</ul></article>'
stacks=''.join(f'<div class="stack-row"><h3>{rich(t["label"])}</h3><div class="stack-tags">'+''.join(f'<span>{e(tag.strip())}</span>' for tag in t['tags'].split('·'))+'</div></div>' for t in cv['tools'])
project_meta=[(0,'L’IA, de bout en bout.','Des chatbots et un callbot, du RAG à l’orchestration d’agents et à l’évaluation.','ai',['RAG','LangGraph','Python','Langfuse']),(1,'Une plateforme. Tout un écosystème.','Architecture, backend .NET, frontend Angular et accompagnement des équipes.','platform',['.NET Core','Angular','DDD','CQRS']),(4,'Du langage naturel à l’automatisation.','Modéliser le langage, traduire des stratégies et construire des outils de trading.','language',['NLP','MQL4/5','C#','TensorFlow'])]
project_art={
'ai':'<div class="art-ai" aria-hidden="true"><svg viewBox="0 0 600 340"><defs><pattern id="project-grid" width="26" height="26" patternUnits="userSpaceOnUse"><path d="M26 0H0V26" fill="none" stroke="currentColor" opacity=".12"/></pattern></defs><rect width="600" height="340" fill="url(#project-grid)"/><g fill="none" stroke="currentColor"><circle cx="300" cy="170" r="104" opacity=".25"/><circle cx="300" cy="170" r="137" opacity=".12"/><path d="M124 170H216M384 170H475M300 43V86M300 254V298" stroke-width="2"/><path d="M164 85L227 125M373 125L438 85M227 218L164 261M373 218L438 261" opacity=".65"/></g><g fill="currentColor"><circle cx="124" cy="170" r="10"/><circle cx="475" cy="170" r="10"/><circle cx="300" cy="43" r="7"/><circle cx="300" cy="298" r="7"/><circle cx="164" cy="85" r="6"/><circle cx="438" cy="85" r="6"/><circle cx="164" cy="261" r="6"/><circle cx="438" cy="261" r="6"/></g><rect x="232" y="116" width="136" height="108" rx="20" class="art-core"/><text x="300" y="180" text-anchor="middle" class="art-letter">AI</text></svg><span class="art-caption">RAG / AGENTS / ÉVALUATIONS</span></div>',
'platform':'<div class="art-platform" aria-hidden="true"><div class="platform-sheet sheet-back"><span>DATA</span><div class="sheet-lines"></div></div><div class="platform-sheet sheet-mid"><span>API</span><div class="sheet-lines"></div></div><div class="platform-sheet sheet-front"><div class="window-dots"><i></i><i></i><i></i></div><span>WEB</span><div class="mock-columns"><i></i><i></i><i></i></div></div><span class="art-caption">ARCHITECTURE / BACKEND / FRONTEND</span></div>',
'language':'<div class="art-language" aria-hidden="true"><div class="language-flow"><span>langage naturel</span><i>↓</i><span class="language-code">stratégie.mql</span><i>↓</i><span>automatisation</span></div><span class="art-caption">LANGAGE / MODÉLISATION / EXÉCUTION</span></div>'}
projects=''
for order,(idx,title,desc,kind,tags) in enumerate(project_meta):
    m=cv['missions'][idx]
    projects+=f'<article class="work-card work-card--{kind} reveal"><div class="work-cover">{project_art[kind]}</div><div class="work-content"><div class="work-meta"><span>{e(m["company"])}</span><span>{e(m["period"])}</span></div><h3>{e(title)}</h3><p>{e(desc)}</p><div class="project-tags">'+''.join(f'<span>{e(tag)}</span>' for tag in tags)+f'</div><button class="text-button" data-open-mission="{idx}">Explorer la mission {arrow()}</button></div></article>'
# All nine positions of the source CV remain visible in the document.
timeline=''
for i,g in enumerate(cv['experience']):
    positions=''
    for r in g['positions']:
        positions+=f'<article class="career-role"><p class="role-period">{e(r["period"])}</p><h4>{rich(r["title"])}</h4>'
        if r.get('description'):positions+=f'<div class="role-description">{rich(r["description"])}</div>'
        if r.get('techs'):positions+=f'<p class="role-stack"><span>Environnement</span>{e(r["techs"])}</p>'
        positions+='</article>'
    timeline+=f'<details class="career-company reveal" {"open" if i==0 else ""}><summary><span class="company-order">0{i+1}</span><span class="company-name">{e(g["company"])}</span><span class="company-meta">{len(g["positions"])} {"expérience" if len(g["positions"])==1 else "expériences"}</span><span class="expand-sign" aria-hidden="true"></span></summary><div class="company-content">{positions}</div></details>'

def mission_body(m):
    bullets=''.join(f'<li>{rich(item)}</li>' for item in m['realisations'])
    content=f'<p class="mission-summary">{rich(m["synthese"])}</p><p class="mission-role"><span>Rôle</span>{e(m["role"])}</p><h4>Réalisations</h4><ul class="mission-list">{bullets}</ul>'
    if m.get('env'):content+=f'<div class="mission-environment"><span>Environnement technique</span><p>{rich(m["env"])}</p></div>'
    return content
archive=''
templates=''
for i,m in enumerate(cv['missions']):
    archive+=f'<details class="archive-mission"><summary><span class="archive-date">{e(m["period"])}</span><span><strong>{e(m["company"])}</strong><span class="archive-title">{rich(m["title"])}</span></span><span class="expand-sign" aria-hidden="true"></span></summary><div class="archive-content">{mission_body(m)}</div></details>'
    templates+=f'<template id="mission-{i}"><p class="eyebrow">{e(m["company"])} / {e(m["period"])}</p><h2 id="dialog-title">{rich(m["title"])}</h2>{mission_body(m)}</template>'
education=''
for d in cv['education']:
    school='<p>'+e(d['school'])+'</p>' if d.get('school') else ''
    education+=f'<li><span class="education-year">{e(d["period"])}</span><div><h4>{rich(d["degree"])}</h4>{school}</div></li>'

languages=''.join(f'<div><h4>{e(l["name"])}</h4><p>{e(l["level"])}</p></div>' for l in cv['languages'])
contact_labels=['Téléphone','E-mail','Adresse','LinkedIn','Mobilité','Nationalité']
contacts=''
for i,c in enumerate(cv['contact']['items']):
    if c.get('href'):
        attrs='target="_blank" rel="noopener noreferrer"' if c['href'].startswith('https:') else ''
        val=f'<a href="{e(c["href"])}" {attrs}>{rich(c["value"])}</a>'
    elif i==0:
        val=f'<a href="tel:+33668422388">{e(c["value"])}</a>'
    else:
        val=rich(c['value'])

    contacts+=f'<div class="contact-detail"><span>{contact_labels[i]}</span><p>{val}</p></div>'
page=f'''<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1c2a48"><meta name="color-scheme" content="light dark">
<title>{e(name)} — Lead AI Engineer</title>
<meta name="description" content="{e(name)}, Lead AI Engineer à Montpellier. IA générative, RAG, agents, architecture logicielle et développement fullstack. Découvrez mon parcours et mes réalisations.">
<meta property="og:title" content="{e(name)} — Lead AI Engineer"><meta property="og:description" content="IA, développement logiciel et architecture. Un parcours, des systèmes, des réalisations."><meta property="og:type" content="website"><meta property="og:locale" content="fr_FR">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="styles.css">
<script>try{{document.documentElement.dataset.theme=localStorage.getItem('em-theme-v2')||'dark'}}catch(e){{}}</script>
<script src="app.js" defer></script>
</head>
<body>
<a class="skip-link" href="#main">Aller au contenu</a>
<div class="reading-progress" aria-hidden="true"><span></span></div>
<header class="site-header"><a class="brand" href="#accueil" aria-label="Etienne Millerioux — accueil"><span class="brand-mark">em<span>.</span></span><span class="brand-name">Etienne<br>Millerioux</span></a>
<nav class="main-nav" id="main-nav" aria-label="Navigation principale"><a href="#expertise">Expertise</a><a href="#realisations">Réalisations</a><a href="#parcours">Parcours</a><a href="#profil">Profil</a><a class="mobile-contact" href="#contact">Contact ↗</a></nav>
<div class="header-actions"><button class="icon-button theme-toggle" aria-label="Activer le thème clair" aria-pressed="true"><span class="theme-icon" aria-hidden="true">◐</span></button><a class="header-contact" href="#contact">Échanger {arrow()}</a><button class="menu-toggle icon-button" aria-label="Ouvrir le menu" aria-expanded="false" aria-controls="main-nav"><span></span><span></span></button></div></header>
<main id="main">
<section class="hero section-shell" id="accueil" aria-labelledby="hero-title">
<div class="hero-copy"><p class="eyebrow hero-eyebrow"><span class="tiny-cross" aria-hidden="true">✳</span> {e(name)} / {e(cv['summary']['main'])}</p>
<h1 id="hero-title">De l’idée<br>à <span class="serif-accent">l’intelligence.</span></h1>
<p class="hero-description">Je conçois et développe des systèmes d’IA, de l’architecture à l’expérience utilisateur.</p>
<p class="hero-disciplines">{e(cv['summary']['sub'])}</p>
<div class="hero-actions"><a class="button button-primary" href="#realisations">Voir mes réalisations <span aria-hidden="true">↓</span></a><a class="button button-quiet" href="assets/cv/index.html" target="_blank" rel="noopener">CV imprimable {arrow()}</a></div>
<div class="hero-location"><span class="location-dot" aria-hidden="true"></span> Montpellier, France <span class="hero-location-sep">/</span> Python & .NET</div></div>
<div class="hero-art"><div class="art-header"><span>CONCEVOIR LES CONNEXIONS</span><button class="art-motion" data-motion aria-label="Mettre en pause l’animation" aria-pressed="false">Pause Ⅱ</button></div><canvas id="intelligence-canvas" aria-hidden="true"></canvas><div class="art-center-label"><span class="art-small-label">MODÈLES / LOGICIEL / ÉQUIPES</span><span>Intelligence<br><em>en mouvement.</em></span></div><div class="art-footer"><span>01 — LLM</span><span>02 — RAG</span><span>03 — AGENTS</span></div><span class="art-corner" aria-hidden="true">↗</span></div>
<div class="hero-bottom"><span>Un parcours entre IA, ingénierie et leadership.</span><a href="#expertise">Explorer <span aria-hidden="true">↓</span></a></div>
</section>
<div class="discipline-strip" aria-label="Domaines d’expertise"><span>IA générative</span><i aria-hidden="true">✳</i><span>Architecture logicielle</span><i aria-hidden="true">✳</i><span>Développement fullstack</span><i aria-hidden="true">✳</i><span>Leadership technique</span></div>
<section class="expertise-section section-shell" id="expertise" aria-labelledby="expertise-title"><div class="section-intro reveal"><p class="eyebrow"><span>01 /</span> Expertise</p><h2 id="expertise-title">Une vision système.<br>Une pratique <span class="serif-accent">de terrain.</span></h2><p>Relier les modèles, le logiciel et les équipes pour construire des solutions complètes.</p></div><div class="expertise-grid">{expertise}</div><div class="stack-block reveal"><div class="stack-heading"><p class="eyebrow">La boîte à outils</p><p>Des technologies au service de la conception.</p></div>{stacks}</div></section>
<section class="work-section section-shell" id="realisations" aria-labelledby="work-title"><div class="section-heading reveal"><div><p class="eyebrow"><span>02 /</span> Réalisations sélectionnées</p><h2 id="work-title">Des idées.<br>Des systèmes <span class="serif-accent">concrets.</span></h2></div><p>Trois angles sur mon travail : intelligence artificielle, plateformes et automatisation.</p></div><div class="project-grid">{projects}</div></section>
<section class="career-section section-shell" id="parcours" aria-labelledby="career-title"><div class="section-heading reveal"><div><p class="eyebrow"><span>03 /</span> Parcours</p><h2 id="career-title">Construire.<br>Apprendre. <span class="serif-accent">Transmettre.</span></h2></div><p>De la conception d’applications métier aux systèmes agentiques, un parcours commencé en 2000.</p></div><div class="career-list">{timeline}</div><details class="full-history reveal"><summary><span>Aller plus loin</span><strong>Les 15 missions, en détail</strong><span class="expand-sign" aria-hidden="true"></span></summary><div class="archive-list">{archive}</div></details></section>
<section class="profile-section section-shell" id="profil" aria-labelledby="profile-title"><div class="profile-main reveal"><div class="portrait-wrap"><img src="assets/portrait.png" alt="Portrait d’Etienne Millerioux" width="311" height="370" loading="lazy"><span class="portrait-caption">ETIENNE MILLERIOUX / MONTPELLIER</span><span class="portrait-symbol" aria-hidden="true">✳</span></div><div class="profile-copy"><p class="eyebrow"><span>04 /</span> Au-delà du code</p><h2 id="profile-title">Des systèmes.<br>Des équipes.<br><span class="serif-accent">Du concret.</span></h2><p>Développement, architecture, gérance d’entreprise et accompagnement des équipes : mon parcours associe la conception technique à la réalité des projets.</p><p>Chez Kalisys, la relation client et le pilotage de solutions. Chez Schneider Electric et Studi, le développement, le leadership technique et le travail avec des équipes locales et offshore.</p></div></div><div class="profile-details reveal"><div class="education-block"><p class="eyebrow">Formation</p><ul>{education}</ul></div><div class="languages-block"><p class="eyebrow">Langues</p>{languages}</div><div class="profile-note"><span aria-hidden="true">↗</span><p>Concevoir ensemble.<br>Faire grandir la solution.<br>Et ceux qui la construisent.</p></div></div></section>
<section class="contact-section" id="contact" aria-labelledby="contact-title"><div class="section-shell"><div class="contact-top"><p class="eyebrow"><span>05 /</span> Contact</p><span class="contact-star" aria-hidden="true">✳</span></div><h2 id="contact-title">Et si on construisait<br><span class="serif-accent">la suite ?</span></h2><div class="contact-main"><a class="email-link" href="mailto:{e(email)}">{e(email)} {arrow()}</a><button class="copy-button" data-copy-email="{e(email)}">Copier l’e-mail <span aria-hidden="true">⧉</span></button></div><div class="contact-grid">{contacts}</div><div class="contact-bottom"><a class="button button-light" href="{e(linkedin)}" target="_blank" rel="noopener noreferrer">Retrouvons-nous sur LinkedIn {arrow()}</a><a class="contact-cv" href="assets/cv/index.html" target="_blank" rel="noopener">Ouvrir le CV original {arrow()}</a></div></div></section>
</main>
<footer class="site-footer section-shell"><a class="footer-brand" href="#accueil">em.</a><p>© 2026 {e(name)} · IA, logiciel & architecture.</p><a href="#accueil">Retour en haut <span aria-hidden="true">↑</span></a></footer>
<dialog class="mission-dialog" aria-labelledby="dialog-title"><div class="dialog-top"><span class="eyebrow">Mission détaillée</span><button class="dialog-close icon-button" aria-label="Fermer la mission"><span aria-hidden="true">×</span></button></div><div class="dialog-content"></div><div class="dialog-bottom"><a href="#contact" class="button button-primary" data-dialog-contact>Échanger sur mon parcours {arrow()}</a></div></dialog>
{templates}
<div class="toast" role="status" aria-live="polite"></div>
</body></html>'''
(ROOT/'index.html').write_text(page,encoding='utf-8')
(ROOT/'assets/favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="15" fill="#dff68a"/><text x="32" y="42" text-anchor="middle" font-family="Arial,sans-serif" font-size="30" font-weight="700" fill="#1c2a48">em.</text></svg>',encoding='utf-8')
print('Generated index.html:',len(page.encode()),'bytes')
