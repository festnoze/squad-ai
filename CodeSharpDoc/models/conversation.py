from typing import List
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain.memory import ConversationBufferMemory
from langchain_core.messages.base import BaseMessage, BaseMessageChunk

class Message:
    def __init__(self, role: str, content: str, elapsed_seconds: int) -> None:
        self.role: str = role
        self.content: str = content
        self.elapsed_seconds: int = elapsed_seconds

class Conversation:
    def __init__(self) -> None:
        self.messages: List[Message] = []

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
    
    def add_new_message(self, role: str, content: str, elapsed_seconds: int) -> None:
        self.messages.append(Message(role, content, elapsed_seconds))

    def to_memory(self, user_role: str, instructions: List[str]) -> ConversationBufferMemory:
        memory = ConversationBufferMemory(self.to_langchain_messages(user_role, instructions))
        return memory
    
    def to_langchain_messages(self, user_role: str, instructions: List[str]) -> List[BaseMessage]:
        messages_array: List[BaseMessage] = []
        if instructions:
            for instruction in instructions:
                messages_array.append(SystemMessage(content=instruction))

        for message in self.messages:
            # Détermine le type de message basé sur le rôle
            if message.role == user_role:
                messages_array.append(AIMessage(message.content))
            else:
                messages_array.append(HumanMessage(message.content))

        # Vérifie que le dernier message provient du rôle opposé
        if self.messages and self.messages[-1].role == user_role:
            raise ValueError(f"The last message cannot be from the {user_role}. It must alternate.")

        return messages_array

    def get_all_messages_as_json(self):
        messages_json = []
        for message in self.messages:
            message_json = {
                "source": message.role,
                "content": message.content
            }
            messages_json.append(message_json)   
        return messages_json #[::-1] #reverse messages' order