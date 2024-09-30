from common_tools.helpers.execute_helper import Execute
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.RAG.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.question_analysis import QuestionAnalysis, QuestionAnalysisPydantic
from common_tools.RAG.rag_service import RAGService

class RAGPreTreatment:
    @staticmethod
    def rag_pre_treatment(rag:RAGService, query:str) -> tuple[QuestionAnalysis, dict]:
        question_analysis, found_metadata, extracted_metadata = Execute.run_parallel(
            (RAGPreTreatment.analyse_query_language, (rag, query)),
            (RAGPreTreatment.analyse_query_metadata, (rag, query)),
            (RAGPreTreatment.extract_explicit_metadata, (query))
        )

        question_analysis.translated_question = extracted_metadata[0].strip()
        metadata = extracted_metadata[1]
        return question_analysis, metadata

    @staticmethod    
    def analyse_query_language(rag:RAGService, question:str) -> QuestionAnalysis:
        prefilter_prompt = file.get_as_str("prompts/rag_language_detection_query.txt", remove_comments=True)
        prefilter_prompt = prefilter_prompt.replace("{question}", question)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            prefilter_prompt, QuestionAnalysisPydantic, QuestionAnalysis
        )
        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(
            "RAG prefiltering", [rag.llm, rag.llm], output_parser, 10, *[prompt_for_output_parser]
        )
        question_analysis = response[0]
        question_analysis['question'] = question
        if question_analysis['detected_language'].__contains__("english"):
            question_analysis['translated_question'] = question
        return QuestionAnalysis(**question_analysis)

    @staticmethod
    def analyse_query_metadata(rag:RAGService, question:str) -> dict:
        return None #todo: implement this method
        prefilter_prompt = file.get_as_str("prompts/rag_metadata_detection_query.txt", remove_comments=True)
        prefilter_prompt = prefilter_prompt.replace("{question}", question)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            prefilter_prompt, QuestionAnalysisPydantic, QuestionAnalysis
        )
        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(
            "RAG prefiltering", [rag.llm, rag.llm], output_parser, 10, *[prompt_for_output_parser]
        )
        return metadata

    @staticmethod   
    def extract_explicit_metadata(question:str) -> tuple[str, dict]:
        filters = {}
        if RagFilteringMetadataHelper.has_manual_filters(question):
            filters, question = RagFilteringMetadataHelper.extract_manual_filters(question)
        else:
            filters = RagFilteringMetadataHelper.get_default_filters()
        return question, filters
