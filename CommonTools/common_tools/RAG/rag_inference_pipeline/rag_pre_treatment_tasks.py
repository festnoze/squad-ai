import json
from typing import Optional, Union
from common_tools.helpers.execute_helper import Execute
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.ressource_helper import Ressource
from common_tools.models.conversation import Conversation
from common_tools.models.question_analysis_base import QuestionAnalysisBase
from common_tools.models.question_rewritting import QuestionRewritting, QuestionRewrittingPydantic
from common_tools.models.question_translation import QuestionTranslation, QuestionTranslationPydantic
from common_tools.rag.rag_inference_pipeline.end_message_ends_pipeline_exception import EndMessageEndsPipelineException
from common_tools.rag.rag_inference_pipeline.greetings_ends_pipeline_exception import GreetingsEndsPipelineException
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.workflows.output_name_decorator import output_name
from common_tools.helpers.txt_helper import txt
from langchain.chains.query_constructor.base import AttributeInfo

class RAGPreTreatment:
    default_filters = {}
    
    @staticmethod
    def rag_static_pre_treatment(rag:RagService, query:Union[str, Conversation], default_filters:dict = {}) -> tuple[QuestionTranslation, dict]:
        question_analysis, extracted_implicit_metadata, extracted_explicit_metadata = Execute.run_parallel(
            (RAGPreTreatment.query_rewritting, (rag, query)),
            (RAGPreTreatment.analyse_query_for_metadata, (rag, query)),
            (RAGPreTreatment.extract_explicit_metadata, (query)),
        )
        
        query_wo_metadata_implicit = extracted_implicit_metadata[0]
        metadata_implicit = extracted_implicit_metadata[1]
        query_wo_metadata_explicit = extracted_explicit_metadata[0]
        metadata_explicit = extracted_explicit_metadata[1]

        merged_metadata = RAGPreTreatment.get_merged_metadata_and_question_analysis(question_analysis, query_wo_metadata_implicit, metadata_implicit, query_wo_metadata_explicit, metadata_explicit)
        return question_analysis, merged_metadata
    
    @staticmethod
    @output_name('analysed_query')
    def query_standalone_rewritten_from_history(rag:RagService, query:Union[str, Conversation]) -> QuestionRewritting:
        query_standalone_rewritten_prompt = Ressource.get_ressource_file_content('create_standalone_and_rewritten_query_from_history_prompt.txt')
        
        query_standalone_rewritten_prompt = RAGPreTreatment._replace_all_categories_in_prompt(query_standalone_rewritten_prompt)
        query_standalone_rewritten_prompt = RAGPreTreatment._replace_query_and_history_in_prompt(query, query_standalone_rewritten_prompt)  
                
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
                        query_standalone_rewritten_prompt, QuestionRewrittingPydantic, QuestionRewritting)

        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(
                'Make standalone and rewritten query', [rag.llm_2, rag.llm_3], output_parser, 10, *[prompt_for_output_parser])
        
        question_rewritting = QuestionRewritting(**response[0])
        print(f'> Standalone query: "{question_rewritting.question_with_context}" and rewritten query: "{question_rewritting.modified_question}"')

        # interupt pipeline if no RAG is needed
        if question_rewritting.question_type == 'salutations':
            print(f'> Salutations detected, ending pipeline')
            raise GreetingsEndsPipelineException()
        elif question_rewritting.question_type == 'fin_echange':
            print(f"> Fin d'échange detected, ending pipeline")
            raise EndMessageEndsPipelineException()
        return question_rewritting

    @staticmethod
    def _replace_query_and_history_in_prompt(query, prompt):
        prompt = prompt.replace('{user_query}', Conversation.get_user_query(query))
        prompt = prompt.replace('{conversation_history}', Conversation.conversation_history_as_str(query, include_current_user_query=False))
        return prompt
    
    @staticmethod
    @output_name('analysed_query')
    def query_standalone_from_history(rag:RagService, query:Union[str, Conversation]) -> QuestionRewritting:
        query_standalone_prompt = Ressource.get_create_standalone_query_from_history_prompt()
        user_query = Conversation.get_user_query(query)
        query_standalone_prompt = query_standalone_prompt.replace('{user_query}', user_query)
        query_standalone_prompt = query_standalone_prompt.replace('{conversation_history}', Conversation.conversation_history_as_str(query, include_current_user_query=False))

        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            query_standalone_prompt, QuestionRewrittingPydantic, QuestionRewritting
        )

        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(
            'Standalone query from history', [rag.llm_2, rag.llm_3], output_parser, 10, *[prompt_for_output_parser]
        )
        question_rewritting = QuestionRewritting(**response[0])
        print(f'> Standalone query: "{question_rewritting.question_with_context}"')

        # interupt pipeline if no RAG is needed
        if question_rewritting.question_type == 'salutations':
            print(f'> Salutations detected, ending pipeline')
            raise GreetingsEndsPipelineException()
        elif question_rewritting.question_type == 'fin_echange':
            print(f"> Fin d'échange detected, ending pipeline")
            raise EndMessageEndsPipelineException()
        return question_rewritting

    @staticmethod
    @output_name('analysed_query')
    def query_rewritting(rag:RagService, analysed_query:QuestionRewritting) -> str:        
        query_rewritting_prompt = RAGPreTreatment._replace_all_categories_in_prompt(analysed_query.question_with_context)

        response = Llm.invoke_chain('Query rewritting', rag.llm_2, query_rewritting_prompt)

        content =  json.loads(Llm.extract_json_from_llm_response(Llm.get_content(response)))
        analysed_query.modified_question = content['modified_question']
        print(f'> Rewritten query: "{analysed_query.modified_question}"')
        return analysed_query

    @staticmethod
    def _replace_all_categories_in_prompt(prompt):
        out_dir = "./outputs/" #todo: not generic enough
        diploms_names = ', '.join(file.get_as_json(out_dir + 'all/all_diplomas_names.json'))
        certifications_names = ', '.join(file.get_as_json(out_dir + 'all/all_certifications_names.json'))
        domains_list = ', '.join(file.get_as_json(out_dir + 'all/all_domains_names.json'))
        sub_domains_list = ', '.join(file.get_as_json(out_dir + 'all/all_sub_domains_names.json'))

        query_rewritting_prompt = Ressource.get_query_rewritting_prompt()
        query_rewritting_prompt = query_rewritting_prompt.replace("{user_query}", prompt)
        query_rewritting_prompt = query_rewritting_prompt.replace("{diplomes_list}", diploms_names)
        query_rewritting_prompt = query_rewritting_prompt.replace("{certifications_list}", certifications_names)
        query_rewritting_prompt = query_rewritting_prompt.replace("{domains_list}", domains_list)
        query_rewritting_prompt = query_rewritting_prompt.replace("{sub_domains_list}", sub_domains_list)
        return query_rewritting_prompt
               
    @staticmethod    
    @output_name('analysed_query')
    def query_translation(rag:RagService, query:Union[str, Conversation]) -> QuestionTranslation:
        user_query = Conversation.get_user_query(query)
        prefilter_prompt = Ressource.get_language_detection_prompt()
        prefilter_prompt = prefilter_prompt.replace("{question}", user_query)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            prefilter_prompt, QuestionTranslationPydantic, QuestionTranslation
        )
        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(
            'query_translation', [rag.llm_1, rag.llm_2, rag.llm_3], output_parser, 10, *[prompt_for_output_parser]
        )
        question_analysis = response[0]
        question_analysis['question'] = user_query
        if question_analysis['detected_language'].__contains__('english'):
            question_analysis['translated_question'] = user_query
        return QuestionTranslation(**question_analysis)

    @staticmethod    
    @output_name('analysed_query') #todo: to replace with above
    def bypassed_query_translation(rag:RagService, query:Union[str, Conversation]) -> QuestionTranslation:
        user_query = Conversation.get_user_query(query)
        question_analysis = QuestionTranslation(query, query, 'request', 'french')
        return question_analysis

    @staticmethod   
    def extract_explicit_metadata(analysed_query:QuestionAnalysisBase) -> tuple[str, dict]:
        filters = {}
        user_query = QuestionAnalysisBase.get_modified_question(analysed_query)
        if RagFilteringMetadataHelper.has_manual_filters(user_query):
            filters, query_wo_metadata = RagFilteringMetadataHelper.extract_manual_filters(user_query)
        else:
            filters = RAGPreTreatment.default_filters
            query_wo_metadata = user_query
        return query_wo_metadata, filters
    
    metadata_infos = None
    @staticmethod
    def analyse_query_for_metadata(rag:RagService, analysed_query:QuestionAnalysisBase) -> tuple[str, dict]:
        if not RAGPreTreatment.metadata_infos:
            RAGPreTreatment.metadata_infos = RagService.build_metadata_infos_from_docs(rag.langchain_documents, 30)
        query = QuestionAnalysisBase.get_modified_question(analysed_query)
        
        self_querying_retriever, query_constructor = rag.build_self_querying_retriever_langchain(rag.llm_2, RAGPreTreatment.metadata_infos)
        
        response_with_filters = Llm.invoke_chain('Analyse metadata', query_constructor, query)
        
        metadata_filters = RagFilteringMetadataHelper.get_filters_from_comparison(response_with_filters.filter, RAGPreTreatment.metadata_infos)
        return response_with_filters.query, metadata_filters
            
    @staticmethod
    def bypassed_analyse_query_for_metadata(rag:RagService, analysed_query:QuestionAnalysisBase) -> tuple[str, dict]:
        query = QuestionAnalysisBase.get_modified_question(analysed_query)
        return Conversation.get_user_query(query), {}
        
    @staticmethod
    def get_merged_metadata_and_question_analysis(query:Union[str, Conversation], analysed_query :QuestionAnalysisBase, query_wo_metadata_from_implicit:str, implicit_metadata:dict, query_wo_metadata_from_explicit:str, explicit_metadata:dict) -> dict:
        if isinstance(query, Conversation):
            query.last_message.content = analysed_query.modified_question
        # if query_wo_metadata_from_explicit:
        #     QuestionAnalysisBase.set_modified_question(analysed_query, query_wo_metadata_from_explicit.strip())
        # elif query_wo_metadata_from_implicit.strip():
        #     QuestionAnalysisBase.set_modified_question(analysed_query, query_wo_metadata_from_implicit.strip())
        merged_metadata_filters = {}
        if explicit_metadata and any(explicit_metadata):
            merged_metadata_filters = explicit_metadata.copy()
        
        if implicit_metadata and any(implicit_metadata):
            for key, value in implicit_metadata.items():
                if key not in merged_metadata_filters:
                    merged_metadata_filters[key] = value

        # Transform academic_level metadata for some cases
        merged_metadata_filters = RAGPreTreatment.transform_academic_level_metadata(merged_metadata_filters)
        print(f"Metadata filters: '{merged_metadata_filters}'")
        return merged_metadata_filters
    
    def transform_academic_level_metadata(metadata):
        if isinstance(metadata, list):
            return [RAGPreTreatment.transform_academic_level_metadata(item) for item in metadata]
        
        academic_level_metadata = metadata.get('academic_level', None)
        if academic_level_metadata:
            if academic_level_metadata == 'pre-graduate' or academic_level_metadata == 'pré-graduate':
                metadata['academic_level'] = 'Bac'
            elif academic_level_metadata == 'BTS':
                metadata['academic_level'] = 'Bac+2'
            elif academic_level_metadata == 'graduate':
                metadata['academic_level'] = 'Bac+3'
        
        if metadata.get('$and'):
            metadata['$and'] = RAGPreTreatment.transform_academic_level_metadata(metadata['$and'])
        if metadata.get('$or'):
            metadata['$or'] = RAGPreTreatment.transform_academic_level_metadata(metadata['$or'])
        if metadata.get('$not'):
            metadata['$not'] = RAGPreTreatment.transform_academic_level_metadata(metadata['$not'])
        return metadata
