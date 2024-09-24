from typing import List, Optional
from common_tools.models.base_desc import BaseDesc

class EnumMemberDesc(BaseDesc):
    def __init__(self, member_name: str, member_value: int):
        super().__init__(name=member_name)
        self.member_name = member_name
        self.member_value = member_value
    
    @staticmethod
    def factory_from_kwargs(**kwargs):
        if 'member_name' in kwargs and 'member_value' in kwargs and len(kwargs) <= 3:
            return EnumMemberDesc(kwargs['member_name'], kwargs['member_value'])
        else:
            raise ValueError('Invalid argument type')
        
    def to_dict(self):
        return {
            "member-name": self.member_name,
            "member-value": self.member_value
        }

class EnumMembersDesc(BaseDesc):
    def __init__(self, members: Optional[List[EnumMemberDesc]] = None):
        super().__init__(name="EnumMembers")
        self.members = members if members is not None else []

    @staticmethod
    def factory_from_kwargs(**kwargs):
        if 'members' in kwargs and len(kwargs) <= 2:
            members = []
            for member in kwargs['members']:
                members.append(EnumMemberDesc.factory_from_kwargs(**member))
            return EnumMembersDesc(members)
        else:
            raise ValueError('Invalid argument type')

    def to_dict(self):
        return {
            "members": [member.to_dict() for member in self.members]
        }