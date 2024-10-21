from typing import Optional, Union
from common_tools.models.message import Message
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain.memory import ConversationBufferMemory
from langchain_core.messages.base import BaseMessage, BaseMessageChunk

class Conversation:
    def __init__(self, messages: list[dict] = None) -> None:
        self.messages: list[Message] = []
        if messages:
            for message in messages:
                self.add_message(Message(message['role'], message['content']))

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
    
    def add_new_message(self, role: str, content: str, elapsed_seconds: int) -> None:
        self.messages.append(Message(role, content, elapsed_seconds))

    @property
    def last_message(self) -> Message:
        return self.messages[-1]
    
    @staticmethod
    def get_user_query(query_or_conv: Optional[Union[str, 'Conversation']]) -> str:
        if isinstance(query_or_conv, str):
            return query_or_conv
        elif isinstance(query_or_conv, Conversation):
            if not any(query_or_conv.messages): 
                raise ValueError("Invalid query, no message found into the conversation")
            if not query_or_conv.last_message.role == "user":
                raise ValueError("Invalid query, last message should be from user")
            return query_or_conv.messages[-1].content
        else:
            raise ValueError("Unsupported query type")
        
    @staticmethod
    def conversation_history_as_str(query_or_conv: Optional[Union[str, 'Conversation']]) -> str:
        if isinstance(query_or_conv, Conversation):
            conversation_history = '\n- '.join([f"{msg.role}: {msg.content}" for msg in query_or_conv.messages[:-1]])
            if not conversation_history: conversation_history = "No history yet"
            full_question = f"### Conversation history: ###\n{conversation_history}\n\n### User current question: ###\n {query_or_conv.last_message.content}" 
        else:
            full_question = query_or_conv
        return full_question
    
    @staticmethod
    def user_queries_history_as_str(query_or_conv: Optional[Union[str, 'Conversation']]) -> str:
        if isinstance(query_or_conv, Conversation):
            conversation_history = '\n- '.join([f"- {msg.content}" for msg in [query for query in query_or_conv.messages[:-1] if query.role == 'user']])
            if not conversation_history: conversation_history = "No history yet"
            full_question = f"### User queries history: ###\n{conversation_history}\n\n### User current question: ###\n {query_or_conv.last_message.content}" 
        else:
            full_question = query_or_conv
        return full_question
        
    def to_memory(self, user_role: str, instructions: list[str]) -> ConversationBufferMemory:
        memory = ConversationBufferMemory(self.to_langchain_messages(user_role, instructions))
        return memory
    
    def to_langchain_messages(self, user_role: str = 'user', instructions: list[str] = None) -> list[BaseMessage]:
        messages_array: list[BaseMessage] = []
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