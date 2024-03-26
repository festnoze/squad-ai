from typing import List
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain.memory import ConversationBufferMemory

class Message:
    def __init__(self, role: str, content: str) -> None:
        self.role: str = role
        self.content: str = content

class Conversation:
    def __init__(self) -> None:
        self.messages: List[Message] = []

    def add_message(self, message: Message) -> None:
        self.messages.append(message)

    def to_memory(self, user_role: str) -> ConversationBufferMemory:
        memory = ConversationBufferMemory(return_messages=True)
        for message in self.messages:
            # Détermine le type de message basé sur le rôle
            if message.role == user_role:
                memory.chat_memory.add_message(HumanMessage(message.content))
            else:
                memory.chat_memory.add_message(AIMessage(message.content))

        # # Vérifie que le dernier message provient du rôle opposé
        # if self.messages and self.messages[-1].role == user_role:
        #     raise ValueError(f"The last message cannot be from the {user_role}. It must alternate.")

        return memory
