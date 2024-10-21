from typing import Optional, Union
from common_tools.helpers.execute_helper import Execute
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.ressource_helper import Ressource
from common_tools.models.conversation import Conversation
from common_tools.rag.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.question_analysis import QuestionAnalysis, QuestionAnalysisPydantic
from common_tools.rag.rag_service import RagService
from common_tools.workflows.output_name_decorator import output_name
from common_tools.helpers.txt_helper import txt
from langchain.chains.query_constructor.base import AttributeInfo

class RAGPreTreatment:
    default_filters = {}
    
    @staticmethod
    def rag_static_pre_treatment(rag:RagService, query:Optional[Union[str, Conversation]], default_filters:dict = {}) -> tuple[QuestionAnalysis, dict]:
        RAGPreTreatment.default_filters = default_filters #todo: think to rather instanciate current class for setting specific filters by app.
        question_analysis, extracted_implicit_metadata, extracted_explicit_metadata = Execute.run_parallel(
            (RAGPreTreatment.analyse_query_language, (rag, query)),
            (RAGPreTreatment.analyse_query_for_metadata, (rag, query)),
            (RAGPreTreatment.extract_explicit_metadata, (query)),
        )
        
        query_wo_metadata_implicit = extracted_implicit_metadata[0]
        explicit_metadata_implicit = extracted_implicit_metadata[1]
        query_wo_metadata_explicit = extracted_explicit_metadata[0]
        explicit_metadata_explicit = extracted_explicit_metadata[1]

        merged_metadata = RAGPreTreatment.get_merged_metadata(question_analysis, query_wo_metadata_implicit, explicit_metadata_implicit, query_wo_metadata_explicit, explicit_metadata_explicit)
        return question_analysis, merged_metadata

    @staticmethod    
    @output_name('analysed_query')
    def analyse_query_language(rag:RagService, query:Optional[Union[str, Conversation]]) -> QuestionAnalysis:
        user_query = Conversation.get_user_query(query)
        prefilter_prompt = Ressource.get_language_detection_prompt()
        prefilter_prompt = prefilter_prompt.replace("{question}", user_query)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            prefilter_prompt, QuestionAnalysisPydantic, QuestionAnalysis
        )
        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(
            "rag prefiltering", [rag.llm, rag.llm], output_parser, 10, *[prompt_for_output_parser]
        )
        question_analysis = response[0]
        question_analysis['question'] = user_query
        if question_analysis['detected_language'].__contains__("english"):
            question_analysis['translated_question'] = user_query
        return QuestionAnalysis(**question_analysis)

    @staticmethod    
    @output_name('analysed_query') #todo: to replace with above
    def bypassed_analyse_query_language(rag:RagService, query:Optional[Union[str, Conversation]]) -> QuestionAnalysis:
        user_query = Conversation.get_user_query(query)
        question_analysis = QuestionAnalysis(query, query, "request", "french")
        return question_analysis

    @staticmethod   
    def extract_explicit_metadata(query:Optional[Union[str, Conversation]]) -> tuple[str, dict]:
        filters = {}
        user_query = Conversation.get_user_query(query)
        if RagFilteringMetadataHelper.has_manual_filters(user_query):
            filters, query_wo_metadata = RagFilteringMetadataHelper.extract_manual_filters(user_query)
        else:
            filters = RAGPreTreatment.default_filters
            query_wo_metadata = user_query
        return query_wo_metadata, filters
    
    metadata_infos = None
    @staticmethod
    def analyse_query_for_metadata(rag:RagService, query:Optional[Union[str, Conversation]], metadata_infos:list[AttributeInfo] = None) -> tuple[str, dict]:
        if not RAGPreTreatment.metadata_infos:
            RAGPreTreatment.metadata_infos = RagService.generate_metadata_info_from_docs(rag.langchain_documents, 30)
        self_querying_retriever, query_constructor = RagService.build_self_querying_retriever(rag, RAGPreTreatment.metadata_infos)
        question = Conversation.get_user_query(query)
        
        response_with_filters = query_constructor.invoke(question)
        
        if response_with_filters.filter:
            txt.print(f"Filters extracted from the query: {response_with_filters.filter}")
        
        metadata_filters = RagFilteringMetadataHelper.get_filters_from_comparison(response_with_filters.filter)
        return response_with_filters.query, metadata_filters
        
    @staticmethod
    def bypassed_analyse_query_for_metadata(rag:RagService, query:Optional[Union[str, Conversation]], metadata_infos:list[AttributeInfo] = None) -> tuple[str, dict]:
        return Conversation.get_user_query(query), {}
        
    @staticmethod
    def get_merged_metadata(question_analysis :QuestionAnalysis, query_wo_metadata_from_implicit:str, implicit_metadata:dict, query_wo_metadata_from_explicit:str, explicit_metadata:dict) -> dict:
        #todo: replace the translated question isn't good
        if query_wo_metadata_from_explicit and query_wo_metadata_from_explicit != question_analysis.question:
            question_analysis.translated_question = query_wo_metadata_from_explicit.strip()
        elif query_wo_metadata_from_implicit:
            question_analysis.translated_question = query_wo_metadata_from_implicit.strip()
        merged = {}
        if explicit_metadata and any(explicit_metadata):
            merged = explicit_metadata.copy()
        
        if implicit_metadata and any(implicit_metadata):
            for key, value in implicit_metadata.items():
                if key not in merged:
                    merged[key] = value
        return merged
