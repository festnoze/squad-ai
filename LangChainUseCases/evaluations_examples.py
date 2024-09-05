from langsmith.schemas import Example, Run
from langsmith.evaluation import evaluate

class EvaluationsExamples:
    def contains_match(run: Run, example: Example) -> dict:
        reference = example.outputs["answer"]
        prediction = run.outputs["output"]
        score = prediction.lower().contains(reference.lower())
        return {"key": "contains_match", "score": score}
    
# def evaluate_all():
# evaluate(
#     <your prediction function>,
#     data="<dataset_name>",
#     evaluators=[exact_match],
# )
