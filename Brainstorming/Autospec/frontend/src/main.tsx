import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { initLang } from "./i18n/i18n";
import { initTheme } from "./i18n/theme";

// Apply the persisted theme + language to <html> before first paint.
initTheme();
initLang();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
