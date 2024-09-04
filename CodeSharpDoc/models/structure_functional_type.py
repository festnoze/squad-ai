from enum import Enum

class StructureFunctionalType(Enum):
    Controller = 0
    Service = 1
    Repository = 2
    TransferObject = 3
    DomainModel = 4
    Test = 5
    Other = 6

    def __str__(self):
        return self.name.lower()