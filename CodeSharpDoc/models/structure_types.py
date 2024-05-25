from enum import Enum

from helpers.txt_helper import txt

class StructureType(Enum):
    Class = 0
    Record = 1
    Interface = 2
    Enum = 3

    def __str__(self):
        return self.name.lower()