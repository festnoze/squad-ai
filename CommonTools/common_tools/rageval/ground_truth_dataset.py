from ragas.testset.synthesizers.generate import TestsetGenerator
from ragas.testset.synthesizers.base_query import simple, reasoning, multi_context

from common_tools.rag.rag_service import RagService

class GroundTruthDataset:
    def __init__(self, rag_service: RagService, testset_generator: TestsetGenerator):
        self.rag_service = rag_service
        KnowledgeGraph 
        self.testset_generator = TestsetGenerator.from_langchain(self.rag_service.inference_llm,
        generator = TestsetGenerator
    generator_llm,
    critic_llm,
    embeddings
)

    def generate(self, question: str, additionnal_context: str = None, metadata_filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None) -> list[Document]:
        return self.rag_service.semantic_vector_retrieval(question, additionnal_context, metadata_filters, give_score, max_retrived_count, min_score, min_retrived_count)

    def generate_testset(self, question: str, additionnal_context: str = None, metadata_filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None, testset_size: int = 100, testset_type: str = "simple") -> list[Document]:
        if testset_type == "simple":
            testset = simple(question, testset_size)
        elif testset_type == "reasoning":
            testset = reasoning(question, testset_size)
        elif testset_type == "multi_context":
            testset = multi_context(question, testset_size)
        else:
            raise ValueError("Invalid testset_type parameter")
        return self.testset_generator.generate(testset, additionnal_context, metadata_filters, give_score, max_retrived_count, min_score, min_retrived_count)