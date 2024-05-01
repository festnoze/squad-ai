from models.base_desc import BaseDesc
from models.method_desc import MethodDesc
from models.prop_desc import PropDesc

class ClassDesc(BaseDesc):
    def __init__(self, class_name: str, interfaces_names: list[str] = [], methods: list[MethodDesc] = [], properties: list[PropDesc] = []):
        super().__init__(name=class_name)
        self.class_name = class_name
        self.interfaces_names = interfaces_names
        self.methods = methods
        self.properties = properties
        
    def __str__(self):
        return f"Name: '{super.name}'"

class InterfaceDesc(BaseDesc):
    def __init__(self, interface_name: str, base_interfaces_names: list[str] = [], methods: list[MethodDesc] = [], properties: list[PropDesc] = []):
        super().__init__(name=interface_name)
        self.interface_name = interface_name
        self.base_interfaces_names = base_interfaces_names
        self.methods = methods
        self.properties = properties
    
    def __str__(self):
        return f"Name: '{super.name}'"