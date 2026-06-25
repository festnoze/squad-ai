import type { Namespace } from "./index";

export const chatPanel: Namespace = {
  roleUser: { en: "You", fr: "Toi" },
  rolePm: { en: "📋 PM", fr: "📋 PM" },
  rolePo: { en: "🏃 PO", fr: "🏃 PO" },
  roleDev: { en: "💻 Dev", fr: "💻 Dev" },
  roleAnalyst: { en: "🔍 Analyst", fr: "🔍 Analyste" },
  roleArchitect: { en: "🏛️ Architect", fr: "🏛️ Architecte" },
  roleQa: { en: "🧪 QA", fr: "🧪 QA" },
  roleCritic: { en: "🧐 Critic", fr: "🧐 Critique" },
  roleJudge: { en: "⚖️ Judge", fr: "⚖️ Juge" },
  roleSystem: { en: "⚙️ System", fr: "⚙️ Système" },

  placeholderSpec: { en: "Reply to the PM…", fr: "Réponds au PM…" },
  placeholderBuild: {
    en: "Give an instruction to the working dev… (applied on the next attempts)",
    fr: "Donne une consigne au dev en cours… (prise en compte aux prochaines tentatives)",
  },
  placeholderFeedback: {
    en: "Give your feedback on the current iteration…",
    fr: "Donne ton feedback sur l'itération en cours…",
  },

  heading: {
    en: "Chat — specification & feedback",
    fr: "Chat — spécification & feedback",
  },
  specModeGroup: { en: "Specification mode", fr: "Mode de spécification" },
  interviewTitle: {
    en: "Socratic interview: clarify the need through a series of targeted questions, dimension by dimension.",
    fr: "Interview socratique : clarifier le besoin par une série de questions ciblées, dimension par dimension.",
  },
  interview: { en: "💬 Interview", fr: "💬 Interview" },
  brainstormingTitle: {
    en: "Brainstorming: the PM/analyst re-questions the need itself (divergence then convergence).",
    fr: "Brainstorming : le PM/analyste re-questionne lui-même le besoin (divergence puis convergence).",
  },
  brainstorming: { en: "🧠 Brainstorming", fr: "🧠 Brainstorming" },

  emptySpec: {
    en: "The PM will ask you questions to frame the need — answer below.",
    fr: "Le PM va te poser des questions pour cadrer le besoin — réponds ci-dessous.",
  },
  emptyBuild: {
    en: "The PM → PO → QA → Dev exchanges will show here. You can also send feedback at any time.",
    fr: "Les échanges PM → PO → QA → Dev s'afficheront ici. Tu peux aussi envoyer un feedback à tout moment.",
  },

  brainstormOfferGroup: {
    en: "Brainstorming proposal",
    fr: "Proposition de brainstorming",
  },
  brainstormOfferLead: {
    en: "💡 Your idea is still open. A ",
    fr: "💡 Ton idée est encore ouverte. Une session de ",
  },
  brainstormOfferWord: { en: "brainstorming", fr: "brainstorming" },
  brainstormOfferTrail: { en: " session to refine it?", fr: " pour l'affiner ?" },
  brainstormTechniques: {
    en: " Techniques: {list}.",
    fr: " Techniques : {list}.",
  },
  brainstormAccept: {
    en: "🧠 Yes, let's explore together",
    fr: "🧠 Oui, on explore ensemble",
  },
  brainstormRefuse: {
    en: "🤖 No, refine autonomously",
    fr: "🤖 Non, affine en autonomie",
  },

  send: { en: "Send", fr: "Envoyer" },
};
