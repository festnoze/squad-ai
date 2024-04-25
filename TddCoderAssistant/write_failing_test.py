from models.acceptance_criterion import AcceptanceCriterion

class WriteFailingTest:
    @staticmethod
    def design_test(criterion: AcceptanceCriterion) -> dict:
        return {}

    @staticmethod
    def write_test_code(test: dict):
        pass

    @staticmethod
    def ensure_test_fails(test_code: str):
        pass
