import { expect, test } from "@playwright/test";

/**
 * End-to-end happy path against the real stack in demo mode (scripted agents).
 * Covers: project creation, the PM→PO→QA→Dev pipeline populating the board,
 * the pause/resume interruption, expandable acceptance criteria with test
 * states, and project deletion.
 */
test("full lifecycle: create, pause/resume, inspect criteria, delete", async ({ page }) => {
  await page.goto("/");

  // If a previous project lingers, switch to the creation screen first.
  const newBtn = page.getByRole("button", { name: "＋ Nouveau" });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();

  // --- Create a project; the pipeline starts automatically.
  await page.getByPlaceholder(/Décris la feature/).fill("Une calculatrice de démonstration");
  await page.getByRole("button", { name: /Démarrer la spécification/ }).click();

  // --- The PO plan eventually populates the board with the scripted stories.
  await expect(page.getByText("Cœur applicatif")).toBeVisible();
  await expect(page.getByTestId("story-US-1")).toBeVisible();
  await expect(page.getByTestId("story-US-2")).toBeVisible();

  // --- Interruption: pause the pipeline, then resume it. The build phase is
  // slow enough (demo delay) to catch a pause between story batches.
  await page.getByRole("button", { name: "⏸ Pause" }).click();
  const resumeBtn = page.getByRole("button", { name: "▶ Reprendre" });
  await expect(resumeBtn).toBeVisible();
  await expect(page.getByText(/en pause/)).toBeVisible();
  await resumeBtn.click();
  await expect(resumeBtn).toBeHidden();

  // --- The whole iteration completes (both stories reach "Terminé").
  await expect(page.getByTestId("story-US-1").getByText("Terminé")).toBeVisible({
    timeout: 20_000,
  });

  // --- Expand US-1, then expand its first acceptance criterion: it must be
  // green (all its tests are green) and show its tests + the Gherkin.
  await page.getByTestId("story-US-1").getByText("Additionner deux nombres").click();
  await expect(page.getByText("La somme de 2 et 3 vaut 5.")).toBeVisible();
  await page.getByTestId("criterion-head-AC-1").click();
  await expect(page.getByText("Tests d'acceptance", { exact: false })).toBeVisible();
  await expect(page.getByText("Feature: Addition")).toBeVisible();
  await expect(
    page.getByTestId("criterion-AC-1").getByTestId("criterion-state").first(),
  ).toHaveText("vert");

  // --- Project management: delete the active project via its chip; its board
  // (and stories) must disappear.
  page.once("dialog", (d) => d.accept());
  // Target the delete button by its title, scoped to the active chip — robust
  // against other chip buttons (archive…) that share the .chip-del look.
  await page.locator(".project-chip.active").getByTitle("Supprimer le projet").click();
  await expect(page.getByTestId("story-US-1")).toBeHidden();
});
