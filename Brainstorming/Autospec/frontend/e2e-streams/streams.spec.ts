import { APIRequestContext, expect, test, Page } from "@playwright/test";

/**
 * ST-17 - browser e2e of the MULTI-STREAM build path (STREAMS=1, scripted
 * agents). The stream-aware demo plan (_PO_PLAN_STREAMS) delivers one US
 * decomposed into a backend task and a frontend task that depends on it
 * (cross-stream dependency). The suite validates the streams UI surface:
 * stream badges on task rows, the task sub-rows themselves, and the story
 * rolling up to done once both tasks land.
 */

const GOAL = "Une calculatrice web : API d'addition et interface React";
const NAME = "Calculatrice streams";

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

async function ensureCreationForm(page: Page) {
  const newBtn = page.getByRole("button", { name: "＋ Nouveau" });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await expect(page.getByRole("heading", { name: "Nouveau projet / feature" })).toBeVisible();
}

async function createProject(page: Page, name: string, goal: string) {
  await ensureCreationForm(page);
  await page.getByPlaceholder("Nom du projet (optionnel)").fill(name);
  await page.getByPlaceholder(/Décris la feature/).fill(goal);
  await page.getByRole("button", { name: /Démarrer la spécification/ }).click();
}

async function gotoEpics(page: Page) {
  const crumb = page.getByRole("button", { name: "Épics" });
  if (await crumb.isEnabled().catch(() => false)) await crumb.click();
}

async function openEpic(page: Page, title: string) {
  await gotoEpics(page);
  const card = page.locator(".epic-card", { hasText: title });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await card.click();
}

test("multi-stream: badges, tasks and cross-stream delivery", async ({ page, request }) => {
  await page.addInitScript(() => localStorage.setItem("autospec.lang", "fr"));
  await page.goto("/");
  page.on("dialog", (d) => d.accept());

  // Hermétique entre --repeat-each : purge les projets restants.
  const projectChips = page.locator(".project-chip");
  await Promise.race([
    projectChips.first().waitFor({ state: "visible", timeout: 5000 }),
    page
      .getByRole("heading", { name: "Nouveau projet / feature" })
      .waitFor({ state: "visible", timeout: 5000 }),
  ]).catch(() => {});
  for (let n = await projectChips.count(); n > 0; n = await projectChips.count()) {
    await projectChips.first().getByTitle("Supprimer le projet").click();
    await page.getByTestId("confirm-accept").click();
    await expect(projectChips).toHaveCount(n - 1);
  }

  await createProject(page, NAME, GOAL);

  // === Le plan stream-aware se matérialise : US-1 avec tâches par stream ====
  await openEpic(page, "Cœur applicatif");
  const story = page.getByTestId("story-US-1");
  await expect(story).toBeVisible({ timeout: 60_000 });

  // UI multi-stream : le filtre par stream n'existe qu'avec ≥ 2 streams.
  const filter = page.getByRole("group", { name: "Filtre par stream" });
  await expect(filter).toBeVisible({ timeout: 60_000 });
  await expect(filter.getByRole("button", { name: /backend/ })).toBeVisible();
  await expect(filter.getByRole("button", { name: /frontend/ })).toBeVisible();

  // Détail de la story (clic sur le TITRE : la carte contient les sous-lignes
  // de tâches, un clic au centre bulle vers la tâche) : les deux tâches sont
  // rendues ; seul le stream NON primaire porte un badge (backend = primaire).
  await story.getByText("Additionner deux nombres (API + UI)").click();
  await expect(page.getByTestId("task-T-1")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("task-T-2")).toBeVisible();
  await expect(page.getByTestId("stream-badge-frontend").first()).toBeVisible();

  // === Le build multi-stream va au bout : la story roule à done =============
  await expect
    .poll(
      async () => {
        const projects = await getJson<Array<{ id: string; phase: string }>>(
          request,
          "/api/projects",
        );
        return projects[0]?.phase ?? "";
      },
      { timeout: 180_000, intervals: [2000] },
    )
    .toMatch(/done|stopped|needs_attention/);

  const projects = await getJson<
    Array<{ stories: Array<{ id: string; effective_status_value?: string; status: string }> }>
  >(request, "/api/projects");
  const us1 = projects[0]?.stories.find((s) => s.id === "US-1");
  expect(us1, "US-1 présente dans le state").toBeTruthy();
  // P2 : le rollup effectif (dérivé des tâches) est exposé par l'API.
  expect(us1!.effective_status_value ?? us1!.status).toBe("done");
});
