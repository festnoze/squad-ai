from models.unit import Unit

class AcceptanceCriterion:
    def __init__(self, name="", description="", unit=None):
        self.name = name
        self.description = description
        self.unit = unit
