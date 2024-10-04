from common_tools.helpers.execute_helper import Execute
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.ressource_helper import Ressource
from common_tools.RAG.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.question_analysis import QuestionAnalysis, QuestionAnalysisPydantic
from common_tools.RAG.rag_service import RAGService

class RAGPreTreatment:
    default_filters = {}
    
    @staticmethod
    def rag_pre_treatment(rag:RAGService, query:str, default_filters:dict = {}) -> tuple[QuestionAnalysis, dict]:
        RAGPreTreatment.default_filters = default_filters #todo: think to make instanciate the class for specific filters by app.
        question_analysis, found_metadata, extracted_metadata = Execute.run_parallel(
            (RAGPreTreatment.analyse_query_language, (rag, query)),
            (RAGPreTreatment.analyse_query_for_metadata, (rag, query)),
            (RAGPreTreatment.extract_explicit_metadata, (query))
        )

        question_analysis.translated_question = extracted_metadata[0].strip()
        metadata = extracted_metadata[1]
        return question_analysis, metadata

    @staticmethod    
    def analyse_query_language(rag:RAGService, query:str) -> QuestionAnalysis:
        prefilter_prompt = Ressource.get_language_detection_prompt()
        prefilter_prompt = prefilter_prompt.replace("{question}", query)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            prefilter_prompt, QuestionAnalysisPydantic, QuestionAnalysis
        )
        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(
            "RAG prefiltering", [rag.inference_llm, rag.inference_llm], output_parser, 10, *[prompt_for_output_parser]
        )
        question_analysis = response[0]
        question_analysis['question'] = query
        if question_analysis['detected_language'].__contains__("english"):
            question_analysis['translated_question'] = query
        return QuestionAnalysis(**question_analysis)

    @staticmethod
    def analyse_query_for_metadata(rag:RAGService, query:str) -> dict:
        return None #todo: implement this method using langchain self querying insead

    @staticmethod   
    def extract_explicit_metadata(query:str) -> tuple[str, dict]:
        filters = {}
        if RagFilteringMetadataHelper.has_manual_filters(query):
            filters, query = RagFilteringMetadataHelper.extract_manual_filters(query)
        else:
            filters = RAGPreTreatment.default_filters
        return query, filters
