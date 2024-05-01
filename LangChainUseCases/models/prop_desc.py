from models.base_desc import BaseDesc

class PropDesc(BaseDesc):
    def __init__(self, prop_name: str, prop_type: str, is_property: bool = False):
        super().__init__(name=prop_name)
        self.prop_name = prop_name
        self.prop_type = prop_type
        self.is_property = is_property
        self.is_field = not is_property
    
    def __str__(self):
        return f"Name: '{super.name}'"