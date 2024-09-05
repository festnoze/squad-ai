from abc import ABC

class BaseDesc(ABC):
    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        return f"Name: '{self.name}'"