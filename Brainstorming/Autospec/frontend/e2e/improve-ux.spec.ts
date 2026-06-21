import { APIRequestContext, expect, Page, test } from "@playwright/test";

/**
 * Focused E2E for the "improve_UX" MVP: the ⚡ Activité lens (steppers per work
 * item), targeted per-item chat (guidance with a delivery status), and the
 * extend-criteria affordance. Runs on the DEFAULT demo flow (no AUTOSPEC_STREAMS):
 * steppers derive each story's stage from `current_stage` (→ "done" once the
 * story is done); storyChat/extend work regardless of streams.
 *
 * Deliberately small — the exhaustive surface lives in autospec.spec.ts; here we
 * only cover the new Activity view + Stepper + targeted chat + extend.
 */

const GOAL = "Une petite calculatrice pour la vue Activité";
const NAME = "Activité UX";

/** Open the creation modal if a project is already selected. */
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
  await dismissBrainstorm(page);
}

/**
 * B-IDEA: when the brainstorming assist is enabled (the demo classifies every
 * idea as "vague"), the spec phase pauses on a Yes/No offer. Decline it so the PM
 * refines autonomously and the pipeline flows to spec/build. No-op when absent.
 */
async function dismissBrainstorm(page: Page) {
  const refuse = page.getByRole("button", { name: /Non, affine en autonomie/ });
  try {
    await refuse.waitFor({ state: "visible", timeout: 15_000 });
  } catch {
    return;
  }
  await refuse.click();
  await expect(refuse).toBeHidden();
}

/** Wipe any pre-existing projects via the API (deterministic — no chip/dialog
 *  races when this spec runs after the exhaustive one against the same backend),
 *  then reload so the bar reflects the clean state. */
async function clearProjects(page: Page, request: APIRequestContext) {
  const existing = (await (await request.get("/api/projects")).json()) as { id: string }[];
  for (const p of existing) {
    await request.delete(`/api/projects/${p.id}`).catch(() => {});
  }
  await page.goto("/");
  await expect(page.locator(".project-chip")).toHaveCount(0);
}

test("improve_UX: Activité stepper + targeted chat + extend", async ({ page, request }) => {
  await page.goto("/");
  page.on("dialog", (d) => d.accept());

  await clearProjects(page, request);

  // === création — la pipeline démarre (spec → build) puis l'itération se termine
  await createProject(page, NAME, GOAL);
  // Le board est hiérarchique (épics → US) ; on attend simplement que la
  // pipeline ait construit l'itération (US-1/US-2 verts → epic « Cœur applicatif »
  // 2/2 terminée(s)). C'est plus robuste que de drill-down dans le board.
  await expect(
    page.locator(".epic-card", { hasText: "Cœur applicatif" }),
  ).toContainText("2/2 terminée(s)", { timeout: 60_000 });

  // === bascule sur la lentille « ⚡ Activité » ===============================
  // Hors BUILD la vue par défaut est « Vision produit » ; on clique l'onglet.
  await page.getByRole("tab", { name: "⚡ Activité" }).click();
  const activity = page.getByRole("region", { name: "Activité" });
  await expect(activity).toBeVisible();
  await expect(page.getByTestId("activity-counts")).toBeVisible();

  // === au moins un Stepper rend une étape (US-1 terminé → cellule « Fini ») ==
  const stepper = page.getByTestId("stepper-US-1");
  await expect(stepper).toBeVisible();
  // Le stepper dérive son étape de current_stage : une story terminée a la
  // cellule terminale « done » en état "done".
  await expect(page.getByTestId("stage-US-1-done")).toHaveAttribute("data-state", "done");
  // Et au moins une cellule d'étape est présente (le track est rendu).
  await expect(stepper.locator(".stepper-cell").first()).toBeVisible();

  // === chat ciblé sur US-1 : la consigne apparaît avec un statut de livraison
  await page.getByTestId("activity-toggle-US-1").click();
  const chatInput = page.getByTestId("item-chat-input-US-1");
  await expect(chatInput).toBeVisible();
  await chatInput.fill("Ajoute un cas limite pour la division par zéro.");
  await page.getByTestId("item-chat-send-US-1").click();
  // La consigne se matérialise dans la liste de guidance avec un data-status
  // (US-1 étant terminé → « too_late », un statut de livraison valide).
  const guidanceEntry = page.getByTestId("guidance-list-US-1").locator(".guidance-entry");
  await expect(guidanceEntry.first()).toBeVisible({ timeout: 30_000 });
  await expect(guidanceEntry.first()).toHaveAttribute(
    "data-status",
    /queued|applied|too_late/,
  );

  // === extend : étendre les critères d'une story encore TODO ================
  // L'évaluateur (E6) planifie un epic de feedback avec une story buildable
  // restée TODO ; on récupère son id via l'API (en l'attendant, la pipeline
  // continue après US-1) pour cibler son affordance.
  type ApiStory = { id: string; status: string; acceptance_criteria?: unknown[] };
  type ApiProject = { id: string; name: string; stories: ApiStory[] };
  // Le backend démo fait du vrai travail git/process pendant le build : une
  // requête peut tomber sur un event-loop momentanément occupé (ECONNRESET /
  // ETIMEDOUT). On retente quelques fois avant d'abandonner.
  const getProjects = async (): Promise<ApiProject[]> => {
    let lastErr: unknown;
    for (let i = 0; i < 5; i++) {
      try {
        const res = await request.get("/api/projects", { timeout: 10_000 });
        return (await res.json()) as ApiProject[];
      } catch (e) {
        lastErr = e;
        await page.waitForTimeout(1000);
      }
    }
    throw lastErr;
  };
  const projectByName = async (): Promise<ApiProject> => {
    const list = await getProjects();
    const p = list.find((x) => x.name === NAME);
    expect(p).toBeTruthy();
    return p!;
  };
  let proj = await projectByName();
  let todo: ApiStory | undefined;
  await expect
    .poll(
      async () => {
        proj = await projectByName();
        todo = proj.stories.find((s) => s.status === "todo");
        return todo ? 1 : 0;
      },
      { timeout: 60_000, message: "une story TODO (epic de feedback) doit apparaître" },
    )
    .toBe(1);
  const tid = todo!.id;
  const before = (todo!.acceptance_criteria ?? []).length;
  // La ligne d'activité de cette story doit être rendue (Activity dérive ses
  // lignes de TOUTES les stories) avant qu'on ouvre son tiroir.
  await expect(page.getByTestId(`activity-row-${tid}`)).toBeVisible({ timeout: 30_000 });

  await page.getByTestId(`activity-toggle-${tid}`).click();
  await page.getByTestId(`extend-${tid}`).click();
  const extendInput = page.getByTestId(`extend-input-${tid}`);
  await expect(extendInput).toBeVisible();
  await extendInput.fill("Le résultat est arrondi à deux décimales.");
  await page.getByTestId(`extend-submit-${tid}`).click();
  // Le formulaire se referme après l'ajout (le bouton « ＋ Étendre » revient).
  await expect(page.getByTestId(`extend-${tid}`)).toBeVisible({ timeout: 30_000 });

  // Vérification côté API : le nombre de critères a augmenté après l'extend.
  const aproj = await projectByName();
  const astory = aproj.stories.find((s) => s.id === tid);
  expect((astory?.acceptance_criteria ?? []).length).toBeGreaterThan(before);

  // === nettoyage ============================================================
  await request.delete(`/api/projects/${proj.id}`, { timeout: 10_000 }).catch(() => {});
});
