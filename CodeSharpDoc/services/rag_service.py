from models.rag_struct import RagMethodDesc
from models.structure_desc import StructureDesc
from langchain_core.language_models import BaseChatModel
#
import langchains.langchain_rag as rag

class RAGService:
    def __init__(self, llm: BaseChatModel, structures: list[StructureDesc]):
        self.llm = llm
        self.rag_methods_desc = []
        for struct in structures:
            for method in struct.methods:
                self.rag_methods_desc.append(RagMethodDesc(method.method_name, method.generated_summary, struct.file_path))
        self.vectorstore = rag.build_vectorstore([meth.to_dict() for meth in self.rag_methods_desc])

                
    def query(self, question: str) -> str:
        retriver = rag.retrieve(self.vectorstore, question, self.llm)
        msg = rag.generate_response_from_retrieval(self.llm, retriver, question)
        return msg.content
        