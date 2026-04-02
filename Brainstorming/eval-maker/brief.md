# Eval Suite Generator — Product Brief

Build an **Eval Suite Generator**: a Python tool that takes a system prompt (or PRD/requirements document) as input, automatically extracts individual rules and instructions, clusters them semantically into thematic groups, generates LLM-as-a-judge evaluator prompts per cluster with scoring rubrics (1-5 per rule), creates tagged test datasets (baseline + edge cases + adversarial scenarios), and pushes the resulting eval suite to Langfuse (datasets + evaluator configs).

**First application target**: the SkillForge tutoring prompt (v28, ~35 rules) located in `input/skillforge-prompt.txt`.

**Output**: a conformity heatmap (scenarios x rules) showing where the system follows or violates its instructions, plus all eval artifacts pushed to Langfuse.

## Technical Constraints

- **Backend**: Python with FastAPI
- **LLM calls**: Use OpenAI API via `OPENAI_API_KEY` (for rule extraction, judge generation, dataset generation)
- **Eval storage**: Langfuse SDK (datasets API, scores API) — credentials in `.env`
- **Database**: SQLite for local state
- **Frontend**: Simple React + Vite for the heatmap visualization
- **Target runtime**: ~3h autonomous build

## Pipeline Architecture

1. **EXTRACT** — Parse the input prompt, identify each atomic rule/instruction (explicit + implicit)
2. **CLUSTER** — Group rules by semantic similarity into 5-7 thematic clusters
3. **GENERATE JUDGES** — For each cluster, produce a judge prompt with scoring rubric (1-5 per rule)
4. **GENERATE DATASETS** — For each rule: positive cases, edge cases, adversarial cases
5. **PUSH TO LANGFUSE** — Upload datasets and eval configs
6. **EXECUTE & VISUALIZE** — Run evals, produce heatmap matrix (scenarios x rules)
