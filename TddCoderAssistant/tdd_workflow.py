import time
from langchain_core.language_models import BaseChatModel
from models.acceptance_criterion import AcceptanceCriterionTestUnit
from plan_tdd_action import PlanTddAction
from write_test import WriteTest
from write_passing_code import WritePassingCode
from refactor_code_and_test import RefactorCodeAndTest

class TddWorkflow:
    @staticmethod
    def write_feature_code_using_tdd(llm: BaseChatModel, feature_description: str) -> tuple[str, str]:
        start_time = time.time()
        code: str = ""
        tests_code: str = ""
        acceptance_criteria: list[AcceptanceCriterionTestUnit] = []
        next_criterion: AcceptanceCriterionTestUnit = AcceptanceCriterionTestUnit()
        stop_sentence = "No more acceptance criteria to implement"
        
        def has_duplicate_name():
            return any(criterion.name == next_criterion.name for criterion in acceptance_criteria)

        while next_criterion.acceptance_criterion_desc != stop_sentence and not has_duplicate_name():
            next_criterion = PlanTddAction.plan_next_acceptance_criterion(llm, feature_description, acceptance_criteria, stop_sentence)            
            print("Test name: '" + next_criterion.unittest_name + "'. Desc: " + next_criterion.acceptance_criterion_desc)            
            WriteTest.create_test_name(llm, next_criterion)        
            WriteTest.create_test_gherkin(llm, next_criterion)
            #test_design = WriteTest.design_test(acceptance_criteria, code, tests_code)
            test_code = WriteTest.write_unittest_code(llm, next_criterion)
            continue
        
            code = WritePassingCode.create_tests_new_concepts_in_code(implementation_plan, code)
            WriteTest.ensure_test_fails(test_code)

            implementation_plan = WritePassingCode.plan_implementation(next_criterion)
            code = WritePassingCode.write_minimal_code(implementation_plan, code)
            WritePassingCode.run_tests()

            acceptance_criteria.append(next_criterion.unit)

            refactorings = RefactorCodeAndTest.identify_refactor_opportunities(implementation_plan)
            RefactorCodeAndTest.apply_refactorings(refactorings)
            RefactorCodeAndTest.ensure_tests_pass()

            next_criterion = PlanTddAction.plan_next_acceptance_criterion(llm, feature_description, acceptance_criteria, stop_sentence)
        
        while next_criterion.description != stop_sentence and len([criterion for criterion in acceptance_criteria if criterion.name == next_criterion.name]) < 2:
            next_criterion = PlanTddAction.plan_next_acceptance_criterion(llm, feature_description, acceptance_criteria, stop_sentence)
            
            print("Test name: '" + next_criterion.name + "'. Desc: " + next_criterion.description)
            acceptance_criteria.append(next_criterion)
            continue

            process_criterion(next_criterion)
        
        end_time = time.time()
        elapsed = LangChainAdapter.get_elapsed_time_seconds(start_time, end_time)
        print(f"Total elapsed time: {elapsed} seconds")
        return (code, tests_code)
