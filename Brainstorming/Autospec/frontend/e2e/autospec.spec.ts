import { expect, test, Page } from "@playwright/test";

/**
 * Exhaustive end-to-end scenario against the real stack in demo mode (scripted
 * agents, every optional phase enabled — see playwright.config.ts env). One
 * scenario walks the whole product surface:
 *
 *  U1  accueil/modale + barre multi-projets + archivage
 *  E3  proposition de composants            E4  exécuteur de setup
 *  E1* (toggle spec — fugace en démo)       I1  budget + jauge 💸
 *  item 7  phase Architecture               item 10 scores de raffinement
 *  PM→PO→QA→Dev (board, critères, Gherkin)  pause/reprise
 *  E6  évaluateur (findings)                E2  analyse d'impact (nouvelle story)
 *  E7  rétrospective (leçons)               item 11 « Continuer le build »
 *  item 1 édition de story                  item 12 diff par story
 *  item 5 visualiseur de code               I2  doc + zip + commit
 *  M1  sélecteur de provider                item 15 archivage
 */

const GOAL = "Une calculatrice de démonstration exhaustive";
const NAME = "Calculatrice exhaustive";

/** Open the creation modal if a project is already selected. */
async function ensureCreationForm(page: Page) {
  const newBtn = page.getByRole("button", { name: "＋ Nouveau" });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await expect(page.getByRole("heading", { name: "Nouveau projet / feature" })).toBeVisible();
}

async function createProject(page: Page, name: string, goal: string, budget?: string) {
  await ensureCreationForm(page);
  await page.getByPlaceholder("Nom du projet (optionnel)").fill(name);
  await page.getByPlaceholder(/Décris la feature/).fill(goal);
  if (budget) await page.getByPlaceholder(/Budget max/).fill(budget);
  await page.getByRole("button", { name: /Démarrer la spécification/ }).click();
}

test("exhaustive: every feature in one scenario", async ({ page, request }) => {
  await page.goto("/");

  // === U1 — création (budget I1) ============================================
  await createProject(page, NAME, GOAL, "10");

  // === E3 — proposition de composants (backend/frontend obligatoires, db opt.)
  const comps = page.locator(".panel.components");
  await expect(comps.getByText("🧱 Composants du produit")).toBeVisible();
  await expect(comps.getByText("API backend")).toBeVisible();
  await expect(comps.getByText(/PostgreSQL/)).toBeVisible();
  await expect(comps.getByText("(optionnel)")).toBeVisible();

  // === pause / reprise (la pipeline est active) =============================
  await page.getByRole("button", { name: "⏸ Pause" }).click();
  await expect(page.getByText(/en pause/)).toBeVisible();
  const resumeBtn = page.getByRole("button", { name: "▶ Reprendre" });
  await expect(resumeBtn).toBeVisible();
  await resumeBtn.click();
  await expect(resumeBtn).toBeHidden();

  // === PM→PO→QA→Dev — le board se peuple ====================================
  await expect(page.getByText("Cœur applicatif")).toBeVisible();
  await expect(page.getByTestId("story-US-1")).toBeVisible();
  await expect(page.getByTestId("story-US-2")).toBeVisible();

  // === I1 — la jauge budget « 💸 $x / $10.00 » apparaît =====================
  await expect(page.getByText(/\/ \$10\.00/)).toBeVisible();

  // === l'itération se termine (US-1 puis US-2 « Terminé ») ==================
  await expect(page.getByTestId("story-US-1").getByText("Terminé")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("story-US-2").getByText("Terminé")).toBeVisible({
    timeout: 60_000,
  });

  // === item 7 — phase Architecture + item 10 — scores de raffinement ========
  await expect(page.getByText("Architecture & qualité")).toBeVisible();
  await expect(page.getByText(/Qualité du plan/)).toBeVisible();
  // Badge qualité du code de la story (raffinement, score démo 90/100).
  await expect(page.getByTestId("story-US-1").getByText(/\/100/)).toBeVisible();

  // === critères d'acceptance + états de test + Gherkin ======================
  await page.getByTestId("story-US-1").getByText("Additionner deux nombres").click();
  await expect(page.getByText("La somme de 2 et 3 vaut 5.")).toBeVisible();
  await page.getByTestId("criterion-head-AC-1").click();
  await expect(page.getByText("Feature: Addition")).toBeVisible();
  await expect(
    page.getByTestId("criterion-AC-1").getByTestId("criterion-state").first(),
  ).toHaveText("vert");

  // === E6 — l'évaluateur a exercé le produit (findings dans le chat) ========
  await expect(page.getByText(/🔬/).first()).toBeVisible();
  // === E7 — la rétrospective a produit des leçons ===========================
  await expect(page.getByText(/Rétrospective d'usine/).first()).toBeVisible();
  // === E6 → E2 — les findings ont alimenté la pipeline d'impact (nouvelle US)
  await expect(page.getByText("Retours utilisateur")).toBeVisible();
  await expect(page.getByText("Prendre en compte le feedback").first()).toBeVisible();

  // === item 1 — édition d'une story (titre) =================================
  await page.getByTestId("story-US-1").getByRole("button", { name: /Éditer/ }).click();
  const titleInput = page.getByTestId("story-US-1").locator(".story-editor input").first();
  await titleInput.fill("Additionner deux nombres (édité)");
  await page.getByTestId("story-US-1").getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Additionner deux nombres (édité)")).toBeVisible();

  // === item 12 — diff par story (commit « story US-1 done ») ================
  await page.getByTestId("story-US-1").getByRole("button", { name: /Diff/ }).click();
  await expect(page.getByText(/📊 Diff — US-1/)).toBeVisible();
  await page.locator(".diff-close").click();
  await expect(page.getByText(/📊 Diff — US-1/)).toBeHidden();

  // === item 5 — visualiseur de code du workspace ============================
  await page.getByRole("button", { name: /Code généré/ }).click();
  await expect(page.getByRole("button", { name: "pyproject.toml" })).toBeVisible();
  await page.getByRole("button", { name: "pyproject.toml" }).click();
  await expect(page.locator(".code-viewer-pre")).toContainText("[project]");
  await page.locator(".code-viewer-close").click();

  // === E4 — exécuteur de setup (composants approuvés → créés) ===============
  await page.getByRole("button", { name: /Créer les composants approuvés/ }).click();
  await expect(page.getByText("créé").first()).toBeVisible({ timeout: 30_000 });

  // === E2 — feedback manuel quand la pipeline est dormante → nouvelle story =
  await expect(page.getByText("Prendre en compte le feedback")).toHaveCount(1);
  const chat = page.getByPlaceholder(/Donne ton feedback/);
  await chat.fill("Ajoute une fonction de multiplication.");
  await chat.press("Enter");
  await expect(page.getByText("Prendre en compte le feedback")).toHaveCount(2, {
    timeout: 30_000,
  });

  // === item 11 — « Continuer le build » via la chip ▶ (construit les US todo)
  // Avant : 2/4 (US-1+US-2 faites, 2 stories de feedback à faire).
  await expect(page.locator(".project-chip.active")).toContainText("2/4");
  await page
    .locator(".project-chip.active")
    .getByTitle(/Reprendre le build des stories restantes/)
    .click();
  // Après : les 4 stories sont terminées.
  await expect(page.locator(".project-chip.active")).toContainText("4/4", {
    timeout: 60_000,
  });

  // === I2 — documentation (tech-writer écrit le README) =====================
  await page.getByRole("button", { name: /📘 Doc/ }).click();
  await expect(page.getByText(/README généré/).first()).toBeVisible({ timeout: 30_000 });

  // === I2 — commit git du workspace (alerte de confirmation) ================
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: /🔀 Commit/ }).click();

  // === I2 — export zip (endpoint, via le contexte requête) ==================
  const projects = await (await request.get("/api/projects")).json();
  const proj = projects.find((p: { name: string }) => p.name === NAME);
  expect(proj).toBeTruthy();
  const zip = await request.get(`/api/projects/${proj.id}/export`);
  expect(zip.status()).toBe(200);
  expect(zip.headers()["content-type"]).toContain("application/zip");

  // === M1 — sélecteur de provider (verrouillé sur « démo » en mode fake) ====
  await expect(page.locator(".provider-select")).toBeVisible();
  await expect(page.locator(".provider-select select")).toBeDisabled();

  // === U1 (multi) — créer un 2e projet : deux chips dans la barre ===========
  await createProject(page, "Projet secondaire", "Un second produit de démo");
  await expect(page.locator(".project-chip")).toHaveCount(2);

  // === item 15 — archivage du 1er projet (terminé) ==========================
  await page
    .locator(".project-chip", { hasText: NAME })
    .getByTitle("Archiver le projet")
    .click();
  // Masqué par défaut, puis ré-affiché via la bascule « 📦 Archivés ».
  await expect(page.locator(".project-chip", { hasText: NAME })).toHaveCount(0);
  await page.getByRole("button", { name: /📦 Archivés/ }).click();
  await expect(page.locator(".project-chip", { hasText: NAME })).toHaveCount(1);

  // === nettoyage — suppression des projets ==================================
  page.on("dialog", (d) => d.accept());
  await page.locator(".project-chip", { hasText: NAME }).getByTitle("Supprimer le projet").click();
  await expect(page.locator(".project-chip", { hasText: NAME })).toHaveCount(0);
});
