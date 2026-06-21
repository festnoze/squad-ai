import { APIRequestContext, expect, test, Page } from "@playwright/test";

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

/**
 * GET + parse JSON with a short retry. The demo backend does real git work
 * (e.g. the commit step blocks the event loop for a beat), so a request fired
 * right after can transiently fail to connect (ECONNRESET / ETIMEDOUT). Retry a
 * few times before giving up.
 */
async function getJson<T>(request: APIRequestContext, url: string): Promise<T> {
  let lastErr: unknown;
  for (let i = 0; i < 6; i++) {
    try {
      const res = await request.get(url, { timeout: 10_000 });
      return (await res.json()) as T;
    } catch (e) {
      lastErr = e;
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  throw lastErr;
}

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
  await dismissBrainstorm(page);
}

/**
 * B-IDEA: when the brainstorming assist is enabled (the demo classifies every
 * idea as "vague"), the spec phase pauses on a Yes/No offer. Decline it so the PM
 * refines the idea autonomously and the pipeline flows straight to the spec/build.
 * No-op when the offer is absent (assist disabled).
 */
async function dismissBrainstorm(page: Page) {
  const refuse = page.getByRole("button", { name: /Non, affine en autonomie/ });
  // The offer appears a beat after "Démarrer" (the assess-idea agent runs first).
  // Wait for it; if it never shows (assist disabled), move on.
  try {
    await refuse.waitFor({ state: "visible", timeout: 15_000 });
  } catch {
    return; // no brainstorm gate (assist off) — nothing to dismiss
  }
  await refuse.click();
  await expect(refuse).toBeHidden();
}

/**
 * Navigate to the board's root « Épics » level (item 17 — the board is a
 * hierarchical drill-down showing a single level at a time). The breadcrumb
 * « Épics » button is disabled when already at that level, so this is a no-op
 * then.
 */
async function gotoEpics(page: Page) {
  const crumb = page.getByRole("button", { name: "Épics" });
  if (await crumb.isEnabled().catch(() => false)) await crumb.click();
}

/** Drill into an epic by title from anywhere in the board. */
async function openEpic(page: Page, title: string) {
  await gotoEpics(page);
  const card = page.locator(".epic-card", { hasText: title });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await card.click();
}

test("exhaustive: every feature in one scenario", async ({ page, request }) => {
  await page.goto("/");
  // Accepter tous les dialogues (confirmations de suppression, alerte commit).
  page.on("dialog", (d) => d.accept());

  // Idempotence : le backend démo conserve son état entre tests (un seul
  // global-setup sous --repeat-each), donc on repart d'une barre vide.
  const projectChips = page.locator(".project-chip");
  await Promise.race([
    projectChips.first().waitFor({ state: "visible", timeout: 5000 }),
    page
      .getByRole("heading", { name: "Nouveau projet / feature" })
      .waitFor({ state: "visible", timeout: 5000 }),
  ]).catch(() => {});
  // Révéler aussi d'éventuels projets archivés avant le nettoyage.
  const archivedToggle = page.getByRole("button", { name: /📦 Archivés/ });
  if (await archivedToggle.isVisible().catch(() => false)) await archivedToggle.click();
  for (let n = await projectChips.count(); n > 0; n = await projectChips.count()) {
    await projectChips.first().getByTitle("Supprimer le projet").click();
    await expect(projectChips).toHaveCount(n - 1);
  }

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

  // === PM→PO→QA→Dev — le board se peuple (navigation hiérarchique, item 17) ==
  // Le board ne montre qu'un niveau à la fois : épics → US d'un epic → détail.
  await openEpic(page, "Cœur applicatif");
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

  // === item 17 — détail de US-1 : critères + états de test + Gherkin =========
  await page.getByTestId("story-US-1").click();
  const detail = page.locator(".story-detail");
  await expect(detail).toBeVisible();
  await expect(page.getByText("La somme de 2 et 3 vaut 5.")).toBeVisible();
  await page.getByTestId("criterion-head-AC-1").click();
  await expect(page.getByText("Feature: Addition")).toBeVisible();
  await expect(
    page.getByTestId("criterion-AC-1").getByTestId("criterion-state").first(),
  ).toHaveText("vert");

  // === item 1 — édition d'une story (titre), au niveau détail ================
  await detail.getByRole("button", { name: /Éditer/ }).click();
  const titleInput = detail.locator(".story-editor input").first();
  await titleInput.fill("Additionner deux nombres (édité)");
  await detail.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Additionner deux nombres (édité)")).toBeVisible();

  // === item 12 — diff par story (commit « story US-1 done ») ================
  await detail.getByRole("button", { name: /Diff/ }).click();
  await expect(page.getByText(/📊 Diff — US-1/)).toBeVisible();
  await page.locator(".diff-close").click();
  await expect(page.getByText(/📊 Diff — US-1/)).toBeHidden();

  // === E6 — l'évaluateur a exercé le produit (findings dans le chat) ========
  await expect(page.getByText(/🔬/).first()).toBeVisible();
  // === E7 — la rétrospective a produit des leçons ===========================
  await expect(page.getByText(/Rétrospective d'usine/).first()).toBeVisible();
  // === E6 → E2 — les findings ont alimenté la pipeline d'impact (nouvel epic)
  // Chaque analyse d'impact planifie un epic de feedback (« Retours utilisateur »)
  // contenant une story buildable ; ici la première, issue de l'évaluateur E6.
  const fbEpics = page.locator(".epic-card", { hasText: "Retours utilisateur" });
  await gotoEpics(page);
  await expect(fbEpics).toHaveCount(1, { timeout: 30_000 });
  await fbEpics.first().click();
  await expect(page.getByText("Prendre en compte le feedback")).toHaveCount(1);

  // === item 5 — visualiseur de code du workspace ============================
  await page.getByRole("button", { name: /Code généré/ }).click();
  await expect(page.getByRole("button", { name: "pyproject.toml" })).toBeVisible();
  await page.getByRole("button", { name: "pyproject.toml" }).click();
  await expect(page.locator(".code-viewer-pre")).toContainText("[project]");
  await page.locator(".code-viewer-close").click();

  // === E4 — exécuteur de setup (composants approuvés → créés) ===============
  await page.getByRole("button", { name: /Créer les composants approuvés/ }).click();
  await expect(page.getByText("créé").first()).toBeVisible({ timeout: 30_000 });

  // === E2 — feedback manuel quand la pipeline est dormante → nouvel epic =====
  // Un feedback envoyé pipeline dormante déclenche une 2e analyse d'impact, qui
  // planifie un second epic de feedback (le board passe à 2 « Retours utilisateur »).
  await gotoEpics(page);
  await expect(fbEpics).toHaveCount(1);
  const chat = page.getByPlaceholder(/Donne ton feedback/);
  await chat.fill("Ajoute une fonction de multiplication.");
  await chat.press("Enter");
  await expect(fbEpics).toHaveCount(2, { timeout: 30_000 });

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
  // UI7 : les actions de livraison sont dans le menu « ⋯ Livraison ».
  await page.getByRole("button", { name: /⋯ Livraison/ }).click();
  await page.getByRole("menuitem", { name: /📘 Doc/ }).click();
  await expect(page.getByText(/README généré/).first()).toBeVisible({ timeout: 30_000 });

  // === I2 — commit git du workspace (toast de confirmation, UI8) ============
  await page.getByRole("button", { name: /⋯ Livraison/ }).click();
  await page.getByRole("menuitem", { name: /🔀 Commit/ }).click();

  // === I2 — export zip (endpoint, via le contexte requête) ==================
  const projects = await getJson<{ id: string; name: string }[]>(request, "/api/projects");
  const proj = projects.find((p) => p.name === NAME);
  expect(proj).toBeTruthy();
  const zip = await request.get(`/api/projects/${proj.id}/export`);
  expect(zip.status()).toBe(200);
  expect(zip.headers()["content-type"]).toContain("application/zip");

  // === M1 — contrôle provider (verrouillé sur « démo » en mode fake, UI10) ===
  await expect(page.locator(".provider-control .provider-trigger")).toBeVisible();
  await expect(page.locator(".provider-control .provider-trigger")).toBeDisabled();

  // === U1 (multi) — créer un 2e projet : les deux figurent dans le sélecteur =
  // UI3 : un projet dormant/terminé vit dans le sélecteur 🗂, pas en chip.
  const reName = new RegExp(NAME.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  await createProject(page, "Projet secondaire", "Un second produit de démo");
  await expect(page.getByRole("option", { name: reName })).toHaveCount(1);
  await expect(page.getByRole("option", { name: /Projet secondaire/ })).toHaveCount(1);

  // === item 15 — archivage du 1er projet (UI3 : sélection → chip → archive) ==
  const selector = page.getByLabel("Sélectionner le projet actif");
  await selector.selectOption(proj.id);
  await page
    .locator(".project-chip", { hasText: NAME })
    .getByTitle("Archiver le projet")
    .click();
  // On bascule sur l'autre projet : le 1er (archivé, non sélectionné) disparaît.
  const after = await getJson<{ id: string; name: string }[]>(request, "/api/projects");
  const sec = after.find((p) => p.name === "Projet secondaire");
  expect(sec).toBeTruthy();
  await selector.selectOption(sec!.id);
  await expect(page.getByRole("option", { name: reName })).toHaveCount(0);
  // Ré-affiché via la bascule « 📦 Archivés ».
  await page.getByRole("button", { name: /📦 Archivés/ }).click();
  await expect(page.getByRole("option", { name: reName })).toHaveCount(1);

  // === nettoyage — suppression via l'API (idempotence des répétitions) ======
  for (const p of after) {
    await request.delete(`/api/projects/${p.id}`);
  }
  await expect(page.getByRole("option", { name: reName })).toHaveCount(0);
});
