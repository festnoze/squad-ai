// Registre de tous les articles du blog
// Utilisé par index.html (listing) et article.html (sidebar + meta)
const BLOG_ARTICLES = [
    {
        slug: "comparatif-techniques-rajeunissement-visage",
        title: "Notox : comparatif des techniques de rajeunissement naturel du visage",
        description: "Kobido, aculifting, yoga du visage, gua sha, LED, radiofréquence... Toutes les alternatives naturelles au botox comparées.",
        category: "Soins visage",
        date: "2026-05-28",
        readTime: "15 min",
        keywords: "notox, kobido, aculifting, lifting naturel visage, soin visage montpellier, alternative botox, massage visage"
    },
    {
        slug: "lifting-naturel-visage-guide-aculifting",
        title: "Lifting naturel du visage : le guide complet de l'aculifting",
        description: "Tout savoir sur l'aculifting : technique, bienfaits, déroulement d'une séance, résultats attendus. Le guide de référence.",
        category: "Aculifting",
        date: "2026-05-28",
        readTime: "12 min",
        keywords: "lifting naturel visage, aculifting, collagène naturel, lifting sans chirurgie, soin visage naturel"
    },
    {
        slug: "notox-alternatives-naturelles-botox",
        title: "Notox : les alternatives naturelles au botox en 2026",
        description: "Le mouvement notox explose. Découvrez toutes les alternatives naturelles au botox et pourquoi l'aculifting s'impose.",
        category: "Tendances",
        date: "2026-05-28",
        readTime: "12 min",
        keywords: "notox, alternative botox naturelle, botox naturel, anti-rides sans injection, biostimulation visage"
    },
    {
        slug: "aculifting-vs-kobido-comparatif",
        title: "Aculifting vs Kobido : quelle technique choisir ?",
        description: "Comparatif objectif entre aculifting et kobido. Deux approches, deux philosophies. Laquelle est faite pour vous ?",
        category: "Soins visage",
        date: "2026-05-28",
        readTime: "11 min",
        keywords: "kobido, aculifting, kobido montpellier, massage visage, lifting naturel, facialiste montpellier"
    },
    {
        slug: "medecine-traditionnelle-chinoise-montpellier",
        title: "Médecine Traditionnelle Chinoise à Montpellier : soins et bienfaits",
        description: "Présentation complète de la MTC : techniques, problématiques accompagnées, déroulement d'une séance au cabinet de Montpellier.",
        category: "MTC",
        date: "2026-05-28",
        readTime: "10 min",
        keywords: "médecine chinoise montpellier, MTC montpellier, médecine alternative montpellier, ventouses, moxibustion"
    },
    {
        slug: "stress-anxiete-medecine-traditionnelle-chinoise",
        title: "Stress et anxiété : l'approche naturelle de la MTC",
        description: "Comment la Médecine Traditionnelle Chinoise aide à soulager le stress et l'anxiété naturellement. Techniques et résultats.",
        category: "Bien-être",
        date: "2026-05-28",
        readTime: "10 min",
        keywords: "anxiété médecine chinoise, stress traitement naturel montpellier, insomnie médecine chinoise, MTC stress"
    },
    {
        slug: "aculifting-resultats-avant-apres-avis",
        title: "Aculifting : résultats avant/après, avis et témoignages",
        description: "Quels résultats attendre de l'aculifting ? Évolution séance par séance, profils types et retours d'expérience.",
        category: "Aculifting",
        date: "2026-05-28",
        readTime: "10 min",
        keywords: "aculifting avant après, aculifting avis, aculifting résultats, lifting naturel avant après"
    },
    {
        slug: "prix-aculifting-mtc-montpellier",
        title: "Prix d'une séance d'aculifting et de MTC à Montpellier",
        description: "Tarifs, déroulement, budget à prévoir et remboursement mutuelle. Toutes les infos pratiques.",
        category: "Pratique",
        date: "2026-05-28",
        readTime: "8 min",
        keywords: "aculifting prix, MTC tarif montpellier, prix médecine chinoise, aculifting montpellier prix"
    },
    {
        slug: "mtc-grossesse-accompagnement-montpellier",
        title: "MTC et grossesse : accompagnement naturel à Montpellier",
        description: "Comment la Médecine Traditionnelle Chinoise accompagne les femmes enceintes trimestre par trimestre.",
        category: "MTC",
        date: "2026-05-28",
        readTime: "12 min",
        keywords: "grossesse médecine chinoise montpellier, MTC grossesse, nausées grossesse traitement naturel"
    },
    {
        slug: "menopause-solutions-naturelles-mtc",
        title: "Ménopause : solutions naturelles en Médecine Traditionnelle Chinoise",
        description: "Bouffées de chaleur, insomnie, irritabilité... La MTC offre une approche naturelle et douce pour accompagner la ménopause.",
        category: "MTC",
        date: "2026-05-28",
        readTime: "12 min",
        keywords: "ménopause médecine chinoise, bouffées chaleur traitement naturel, alternative THS, ménopause MTC"
    },
    {
        slug: "faq-aculifting-medecine-traditionnelle-chinoise",
        title: "FAQ complète : aculifting et Médecine Traditionnelle Chinoise",
        description: "19 questions-réponses sur l'aculifting et la MTC : prix, déroulement, résultats, contre-indications, remboursement.",
        category: "Pratique",
        date: "2026-05-28",
        readTime: "15 min",
        keywords: "aculifting avis, aculifting prix, MTC remboursée, aculifting douloureux, médecine chinoise montpellier"
    }
];
