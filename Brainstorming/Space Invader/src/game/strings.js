// Tous les libelles francais du jeu (D06). Un seul objet plat de chaines :
// le HUD injecte automatiquement dans le DOM toute cle citee par un attribut
// data-str, et lit les autres a la demande.
//
// Les accents sont autorises ici (ce sont des chaines affichees).
// Aucun tiret cadratin : uniquement "-".

export const STR = {
  // --- Ecran titre -----------------------------------------------------
  title: "TERRAFORM ODYSSEY",
  titleEyebrow: "MISSION ARCHE 09",
  tagline: "Douze corps. Une seule chance de recommencer.",
  briefingTitle: "BRIEFING",
  briefing:
    "Terra Prime est perdue : les océans se sont retirés, les forêts ont brûlé. Votre vaisseau de reconnaissance emporte les dernières semences de l'humanité. Quelque part dans ce système, un monde a déjà fait le travail à notre place.",
  briefingElements:
    "Une planète n'est déclarée terraformable que si vous y confirmez les trois éléments : océans liquides, végétation arborée et vie animale.",
  briefingStep1: "Sélectionnez une cible dans le panneau de navigation.",
  briefingStep2: "Descendez en atmosphère et approchez la surface.",
  briefingStep3: "Maintenez F pour analyser ce que vous survolez.",
  qualityLabel: "QUALITÉ GRAPHIQUE",
  qualityLow: "Basse",
  qualityMedium: "Moyenne",
  qualityHigh: "Haute",
  qualityUltra: "Ultra",
  startButton: "DÉCOLLER",
  controlsTitle: "COMMANDES",
  loadingText: "Génération du système Helios Prime...",

  // --- Titres de panneaux ----------------------------------------------
  planetTitle: "CORPS SURVOLÉ",
  navTitle: "NAVIGATION",
  targetTitle: "CIBLE",
  mapTitle: "CARTOGRAPHIE",
  telemetryTitle: "TÉLÉMÉTRIE",
  elementsTitle: "MARQUEURS BIOLOGIQUES",
  helpTitle: "COMMANDES",
  helpFooter: "Appuyez sur H pour reprendre les commandes.",

  // --- Libelles de telemetrie ------------------------------------------
  labelSpeed: "VITESSE",
  labelAltitude: "ALTITUDE",
  labelThrust: "POUSSÉE",
  labelAtmo: "ATMOSPHÈRE",
  labelBiome: "BIOME",
  labelLocalTime: "HEURE LOCALE",
  labelTemp: "TEMPÉRATURE",
  labelType: "CLASSE",
  labelVertical: "VITESSE VERTICALE",
  labelGForce: "ACCÉLÉRATION",

  // --- Valeurs de remplacement -----------------------------------------
  deepSpace: "ESPACE PROFOND",
  dash: "- - -",
  noTarget: "AUCUNE CIBLE",
  unknown: "INCONNU",
  vacuum: "VIDE",
  noAtmosphere: "SANS ATMOSPHÈRE",
  day: "JOUR",
  night: "NUIT",

  // --- Les trois elements ----------------------------------------------
  elOcean: "OCÉANS",
  elTrees: "ARBRES",
  elFauna: "VIE ANIMALE",

  // --- Scan -------------------------------------------------------------
  scanning: "ANALYSE",
  scan_ocean: "ANALYSE DES OCÉANS",
  scan_trees: "ANALYSE DE LA VÉGÉTATION",
  scan_fauna: "ANALYSE DE LA FAUNE",
  scanAborted: "Analyse interrompue.",

  // --- Messages de decouverte -------------------------------------------
  foundOcean: "Océans confirmés : eau liquide en surface.",
  foundTrees: "Végétation arborée confirmée : photosynthèse active.",
  foundFauna: "Vie animale confirmée : signatures de mouvement.",
  foundOceanShort: "Océans confirmés",
  foundTreesShort: "Arbres confirmés",
  foundFaunaShort: "Vie animale confirmée",
  allFound: "Les trois marqueurs sont validés.",

  // --- Indices contextuels ----------------------------------------------
  hintScanKey: "Maintenez F pour lancer une analyse.",
  hintOcean: "Descends sous 900 m au-dessus de l'eau pour analyser.",
  hintTrees: "Approche-toi des arbres.",
  hintFauna: "Cherche du mouvement au sol.",
  hintDescend: "Descends vers la surface pour analyser.",
  hintNoLife: "Ce monde ne porte aucun marqueur biologique. Change de cible.",
  hintNoAtmo: "Aucune atmosphère : rien ne peut vivre ici.",
  hintSelectTarget: "Choisis une cible et engage la vitesse pulse (X).",
  hintPulse: "Hors gravité : X pour la vitesse pulse.",
  hintPullUp: "Alerte de proximité : redresse.",
  hintGasGiant: "Géante gazeuse : pas de sol, seulement des turbulences.",
  hintLeavePlanet: "Reprends de l'altitude pour quitter l'orbite.",

  // --- Toasts d'evenement ------------------------------------------------
  toastEnterAtmo: "Entrée atmosphérique.",
  toastLeaveAtmo: "Sortie d'atmosphère.",
  toastLanded: "Vaisseau posé.",
  toastTakeoff: "Décollage.",
  toastWarp: "Vitesse pulse engagée.",
  toastWarpEnd: "Vitesse pulse coupée.",
  toastApproach: "Approche du corps sélectionné.",
  toastTargetChanged: "Nouvelle cible verrouillée.",
  toastBarren: "Aucun marqueur biologique détecté ici.",
  toastAlarm: "Alerte de proximité.",
  toastHelp: "H : aide des commandes.",

  // --- Ecran de victoire -------------------------------------------------
  winEyebrow: "TRANSMISSION VERS L'ARCHE",
  winTitle: "MONDE TERRAFORMABLE CONFIRMÉ",
  winLead:
    "Océans, forêts, faune : les trois marqueurs sont validés sur le même monde. Le convoi de colonisation peut appareiller.",
  winLabelPlanet: "PLANÈTE",
  winLabelTime: "TEMPS DE MISSION",
  winLabelVisited: "CORPS VISITÉS",
  winLabelDistance: "DISTANCE PARCOURUE",
  winFooter: "Rapport archivé. Fin de la reconnaissance.",
  restartButton: "NOUVELLE SEED",
};

export default STR;
