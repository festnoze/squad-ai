from pydantic import RootModel
from typing import List

class StringsListPydantic(RootModel[List[str]]):
    pass


class DictListPydantic(RootModel[List[dict[str, str]]]):
    pass