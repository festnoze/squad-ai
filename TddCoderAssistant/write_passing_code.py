from models.acceptance_criterion import AcceptanceCriterionTestUnit
from models.implementation_plan import ImplementationPlan


class WritePassingCode:
    @staticmethod
    def plan_implementation(criterion: AcceptanceCriterionTestUnit) -> ImplementationPlan:
        return {}
    

    @staticmethod
    def write_minimal_code(implementation_plan: ImplementationPlan, actual_code: str) -> str:
        code = actual_code
        if not WritePassingCode.verify_code_compilation(code):
            return WritePassingCode.write_minimal_code(implementation_plan, actual_code)
        return code
    
    @staticmethod
    def verify_code_compilation(code: str) -> bool:
        return True

    @staticmethod
    def run_tests():
        pass
