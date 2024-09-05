from models.unit import Unit

class AcceptanceCriterionTestUnit:
    def __init__(self, acceptance_criterion_desc="", unittest_name="", gherkin_code = "", unittest_code = "", unit=None):
        self.acceptance_criterion_desc = acceptance_criterion_desc
        self.unittest_name = unittest_name
        self.gherkin_code = gherkin_code
        self.unittest_code = unittest_code
        self.unit = unit
