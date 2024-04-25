
from models.acceptance_criterion import AcceptanceCriterion
from plan_tdd_action import PlanTddAction
from write_failing_test import WriteFailingTest
from write_passing_code import WritePassingCode
from refactor_code_and_test import RefactorCodeAndTest
from langchains.langchain_adapter_type import LangChainAdapterType
from langchains.langchain_adapter import LangChainAdapter

class TddWorkflow:
    @staticmethod
    def write_code_for_feature(feature_description):
        lc = LangChainAdapter(adapter_type= LangChainAdapterType.Ollama, llm_model_name= "nous-hermes2", temperature= 0, timeout_seconds= 40)
        implemented_acceptance_criteria = []
        next_criterion = AcceptanceCriterion()
        while next_criterion is not None:
            next_criterion = PlanTddAction.plan_next_action(lc.llm, feature_description, implemented_acceptance_criteria)
            implemented_acceptance_criteria.append(next_criterion)
            continue
            test_design = WriteFailingTest.design_test(next_criterion)
            test_code = WriteFailingTest.write_test_code(test_design)
            code = WritePassingCode.create_tests_new_concepts_in_code(implementation_plan, code)
            WriteFailingTest.ensure_test_fails(test_code)

            implementation_plan = WritePassingCode.plan_implementation(next_criterion)
            code = WritePassingCode.write_minimal_code(implementation_plan, code)
            WritePassingCode.run_tests()

            implemented_acceptance_criteria.append(next_criterion.unit)

            refactorings = RefactorCodeAndTest.identify_refactor_opportunities(implementation_plan)
            RefactorCodeAndTest.apply_refactorings(refactorings)
            RefactorCodeAndTest.ensure_tests_pass()

            next_criterion = PlanTddAction.plan_next_action(lc.llm, feature_description, implemented_acceptance_criteria)

if __name__ == "__main__":
    workflow = TddWorkflow()
    workflow.write_feature_code_using_tdd("Add a new string calculator feature")
