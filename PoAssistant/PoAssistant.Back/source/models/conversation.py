from typing import List
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain.memory import ConversationBufferMemory

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
    
    def add_message(self, role: str, content: str, elapsed_seconds: int) -> None:
        self.messages.append(Message(role, content, elapsed_seconds))

    def to_memory(self, user_role: str, *instructions: str) -> ConversationBufferMemory:
        memory = ConversationBufferMemory()
        if instructions:
            messages = [SystemMessage(content=instruction) for instruction in instructions]
            memory = ConversationBufferMemory(messages= messages)            

        if (len(self.messages) > 1):
            for message in self.messages[:-1]:
                # Détermine le type de message basé sur le rôle
                if message.role == user_role:
                    memory.chat_memory.add_message(AIMessage(message.content))
                else:
                    memory.chat_memory.add_message(HumanMessage(message.content))

        # Vérifie que le dernier message provient du rôle opposé
        if self.messages and self.messages[-1].role == user_role:
            raise ValueError(f"The last message cannot be from the {user_role}. It must alternate.")

        return memory

    def get_all_messages_as_json(self):
        messages_json = []
        for message in self.messages:
            message_json = {
                "source": message.role,
                "content": message.content
            }
        messages_json.append(message_json)   
        return messages_json #[::-1] #reverse messages' order