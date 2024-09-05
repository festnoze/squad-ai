from enum import Enum

class FileAlreadyExistsPolicy(Enum):
    Override = 1
    Skip = 2
    AutoRename = 3
    Fail = 4
