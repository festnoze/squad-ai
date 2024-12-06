from enum import Enum

class VectorDbType(Enum):
    ChromaDB = "chroma"
    Qdrant = "qdrant"
    Pinecone = "pinecone"