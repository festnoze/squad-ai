import { useState } from "react";
import {
  AcceptanceCriterion,
  criterionState,
  Epic,
  TestState,
  UserStory,
} from "../types";

const STATUS_LABEL: Record<string, string> = {
  todo: "À faire",
  in_progress: "Dev en cours",
  red: "Tests rouges",
  green: "Tests verts",
  done: "Terminé",
  failed: "Échec",
};

const TEST_STATE_LABEL: Record<TestState, string> = {
  nonexistent: "inexistant",
  red: "rouge",
  green: "vert",
};

const TEST_STATE_ICON: Record<TestState, string> = {
  nonexistent: "○",
  red: "●",
  green: "●",
};

function CriterionRow({
  story,
  criterion,
}: {
  story: UserStory;
  criterion: AcceptanceCriterion;
}) {
  const [open, setOpen] = useState(false);
  const state = criterionState(story, criterion);
  const tests = story.test_plan.filter((t) => t.criteria.includes(criterion.id));

  return (
    <div className={`criterion state-${state}`}>
      <div className="criterion-head" onClick={() => setOpen(!open)}>
        <span className={`state-dot state-${state}`}>{TEST_STATE_ICON[state]}</span>
        <span className="criterion-text">{criterion.text}</span>
        <span className={`state-tag state-${state}`}>{TEST_STATE_LABEL[state]}</span>
        <span className="criterion-expander">{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <div className="criterion-body">
          <h5>Tests d'acceptance ({tests.length})</h5>
          {tests.length === 0 ? (
            <p className="placeholder small">
              Aucun test unitaire rattaché — couvert par le test fonctionnel Gherkin ci-dessous.
            </p>
          ) : (
            <ul className="criterion-tests">
              {tests.map((t) => (
                <li key={t.id}>
                  <span className={`state-dot state-${t.status}`}>
                    {TEST_STATE_ICON[t.status]}
                  </span>
                  <span className="test-layer">{t.layer || "?"}</span>
                  <span className="test-desc">{t.description}</span>
                  {t.mocks.length > 0 && (
                    <span className="test-mocks"> · mocks : {t.mocks.join(", ")}</span>
                  )}
                  <span className={`state-tag state-${t.status}`}>
                    {TEST_STATE_LABEL[t.status]}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {story.gherkin && (
            <>
              <h5>Gherkin associé</h5>
              <pre className="gherkin">{story.gherkin}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function StoryCard({ story }: { story: UserStory }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`story status-${story.status}`}>
      <div className="story-head" onClick={() => setOpen(!open)}>
        <span className="story-id">{story.id}</span>
        <span className="story-right">
          <span className={`prio prio-${story.priority}`} title="Priorité kanban (1=haute)">
            P{story.priority}
          </span>
          <span className={`badge badge-${story.status}`}>{STATUS_LABEL[story.status]}</span>
        </span>
      </div>
      <div className="story-title" onClick={() => setOpen(!open)}>
        {story.title}
      </div>
      {story.depends_on.length > 0 && (
        <div className="story-deps">⛓ dépend de {story.depends_on.join(", ")}</div>
      )}
      {open && (
        <div className="story-details">
          <p>{story.description}</p>
          {story.acceptance_criteria.length > 0 && (
            <>
              <h4>Critères d'acceptance</h4>
              <div className="criteria">
                {story.acceptance_criteria.map((c) => (
                  <CriterionRow key={c.id} story={story} criterion={c} />
                ))}
              </div>
            </>
          )}
          {story.last_error && (
            <>
              <h4>Dernière erreur</h4>
              <pre className="error-output">{story.last_error}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  epics: Epic[];
  stories: UserStory[];
}

export function Board({ epics, stories }: Props) {
  if (epics.length === 0) {
    return (
      <div className="panel board empty">
        <h2>Board Epics / User stories</h2>
        <p className="placeholder">Le PO n'a pas encore produit de plan.</p>
      </div>
    );
  }
  return (
    <div className="panel board">
      <h2>Board Epics / User stories</h2>
      <div className="epics">
        {epics.map((epic) => (
          <div key={epic.id} className="epic">
            <div className="epic-head">
              <span className="epic-id">{epic.id}</span>
              <span className="epic-iter">itération {epic.iteration}</span>
            </div>
            <div className="epic-title">{epic.title}</div>
            <div className="stories">
              {stories
                .filter((s) => s.epic_id === epic.id)
                .map((s) => (
                  <StoryCard key={s.id} story={s} />
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
