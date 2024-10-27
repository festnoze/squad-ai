from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric

def test_answer_relevancy():
    answer_relevancy_metric = AnswerRelevancyMetric(threshold=0.5)
    test_case = LLMTestCase(
        input="quels bts en RH ?",
        actual_output="""\
        Graduate Assistant RH : https://www.studi.com/fr/formation/politique-rh-recrutement/graduate-assistant-rh
        Graduate Assistant RH et Juridique : https://www.studi.com/fr/formation/juridique/graduate-assistant-rh-et-juridique""",
        retrieval_context=[
            "Graduate Assistant RH : https://www.studi.com/fr/formation/politique-rh-recrutement/graduate-assistant-rh",
            "https://www.studi.com/fr/formation/juridique/graduate-assistant-rh-et-juridique"
        ]
    )
    assert_test(test_case, [answer_relevancy_metric])