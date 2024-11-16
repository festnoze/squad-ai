from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass
from typing import List, Optional
# Inherits (kind of): from langchain.chains.query_constructor.base import AttributeInfo

list_possible_values_french_str = "\nVoici toutes les valeurs possibles pour cette metadata, formatée ainsi : • 'valeur possible pour la meta-data' (optionnel: description de la valeur) :"
class MetadataDescription: 
    """Information about an existing metadata. 
    Extends langchain 'AttributeInfo' class."""
    name: str
    description: str
    type: str = "str"
    possible_values: Optional[list[str]] = None

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True)
    
    def __init__(self, name: str, description: str, type: str = 'str', possible_values: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.type = type
        self.possible_values = possible_values
        self.possible_values_as_str = ''
        if possible_values and any(possible_values):
            self.possible_values_as_str = list_possible_values_french_str + '\n\t• ' + '\n\t• '.join([f"'{content}'" for content in possible_values])

    def to_pydantic(self):
        return MetadataDescriptionPydantic(
            name=self.name,
            description=self.description,
            type=self.type,
            possible_values_as_str=self.possible_values_as_str
        )
    
    def to_json(self):
        json_dict = super(self).to_json()
        json_dict['possible_values'] = self.possible_values_as_str
        return json_dict

class MetadataDescriptionPydantic(BaseModel): 
    """Information about an existing metadata. 
    Extends langchain 'AttributeInfo' class."""
    name: str
    description: str
    type: str = "str"
    possible_values_as_str: Optional[str] = None

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True)
    
    def __init__(self, **data):
        possible_values_as_str = data.get("possible_values_as_str", None)
        if possible_values_as_str:
            data["description"] += possible_values_as_str
        super().__init__(**data)