import type { Namespace } from "./index";

export const codeViewer: Namespace = {
  generatedCode: { en: "Generated code", fr: "Code généré" },
  noFiles: { en: "No files.", fr: "Aucun fichier." },
  truncated: { en: "(file truncated)", fr: "(fichier tronqué)" },
  selectFile: { en: "Select a file.", fr: "Sélectionnez un fichier." },
  reveal: { en: "Open in Explorer", fr: "Ouvrir dans l'explorateur" },
  revealHint: {
    en: "Reveal the selected file or folder in the OS file manager",
    fr: "Afficher le fichier ou dossier sélectionné dans l'explorateur du système",
  },
  revealed: { en: "Opened in file manager", fr: "Ouvert dans l'explorateur" },
  copyPath: { en: "Copy path", fr: "Copier le chemin" },
  copyPathHint: {
    en: "Copy the full absolute path of the selection",
    fr: "Copier le chemin absolu complet de la sélection",
  },
  pathCopied: { en: "Path copied to clipboard", fr: "Chemin copié dans le presse-papier" },
};
