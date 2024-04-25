
from langchains.langchain_adapter import LangChainAdapter
from models.acceptance_criterion import AcceptanceCriterion
from plan_tdd_action import PlanTddAction
from write_failing_test import WriteFailingTest
from write_passing_code import WritePassingCode
from refactor_code_and_test import RefactorCodeAndTest

class TddWorkflow:
    @staticmethod
    def write_feature_code_using_tdd(lc: LangChainAdapter, feature_description: str) -> tuple[str, str]:
        implemented_acceptance_criteria: list[AcceptanceCriterion] = []
        next_criterion: AcceptanceCriterion = AcceptanceCriterion()
        stop_sentence = "No more acceptance criteria to implement"
        
        def has_duplicate_name():
            return any(criterion.name == next_criterion.name for criterion in implemented_acceptance_criteria)

        while next_criterion.description != stop_sentence and not has_duplicate_name():
            next_criterion = PlanTddAction.plan_next_action(lc, feature_description, implemented_acceptance_criteria, stop_sentence)
            
            print("Test name: '" + next_criterion.name + "'. Desc: " + next_criterion.description)
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

            next_criterion = PlanTddAction.plan_next_action(lc, feature_description, implemented_acceptance_criteria, stop_sentence)
        
        while next_criterion.description != stop_sentence and len([criterion for criterion in implemented_acceptance_criteria if criterion.name == next_criterion.name]) < 2:
            next_criterion = PlanTddAction.plan_next_action(lc, feature_description, implemented_acceptance_criteria, stop_sentence)
            
            print("Test name: '" + next_criterion.name + "'. Desc: " + next_criterion.description)
            implemented_acceptance_criteria.append(next_criterion)
            continue

            process_criterion(next_criterion)
        
        return ("", "")
