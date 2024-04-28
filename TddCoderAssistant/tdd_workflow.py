import time
from langchains.langchain_adapter import LangChainAdapter
from models.acceptance_criterion import AcceptanceCriterionTestUnit
from plan_tdd_action import PlanTddAction
from write_test import WriteTest
from write_passing_code import WritePassingCode
from refactor_code_and_test import RefactorCodeAndTest

class TddWorkflow:
    @staticmethod
    def write_feature_code_using_tdd(lc: LangChainAdapter, feature_description: str) -> tuple[str, str]:
        start_time = time.time()
        code: str = ""
        tests_code: str = ""
        acceptance_criteria: list[AcceptanceCriterionTestUnit] = []
        next_criterion: AcceptanceCriterionTestUnit = AcceptanceCriterionTestUnit()
        stop_sentence = "No more acceptance criteria to implement"
        
        def has_duplicate_name():
            return any(criterion.name == next_criterion.name for criterion in acceptance_criteria)

        while next_criterion.description != stop_sentence and not has_duplicate_name():
            acceptance_criterion = PlanTddAction.plan_next_acceptance_criterion(lc, feature_description, acceptance_criteria, stop_sentence)            
            #print("Test name: '" + next_criterion.name + "'. Desc: " + next_criterion.description)            
            WriteTest.create_test_name(lc, acceptance_criterion)        
            WriteTest.create_test_gherkin(lc, acceptance_criterion)
            #test_design = WriteTest.design_test(acceptance_criteria, code, tests_code)
            test_code = WriteTest.write_unittest_code(lc, acceptance_criterion)
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

            next_criterion = PlanTddAction.plan_next_acceptance_criterion(lc, feature_description, acceptance_criteria, stop_sentence)
        
        while next_criterion.description != stop_sentence and len([criterion for criterion in acceptance_criteria if criterion.name == next_criterion.name]) < 2:
            next_criterion = PlanTddAction.plan_next_acceptance_criterion(lc, feature_description, acceptance_criteria, stop_sentence)
            
            print("Test name: '" + next_criterion.name + "'. Desc: " + next_criterion.description)
            acceptance_criteria.append(next_criterion)
            continue

            process_criterion(next_criterion)
        
        end_time = time.time()
        elapsed = LangChainAdapter.get_elapsed_time_seconds(start_time, end_time)
        print(f"Total elapsed time: {elapsed} seconds")
        return (code, tests_code)
