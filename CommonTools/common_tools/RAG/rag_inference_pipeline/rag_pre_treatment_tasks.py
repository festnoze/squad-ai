import json
import os
from typing import Optional, Union
from common_tools.helpers.execute_helper import Execute
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.rag_bm25_retriever_helper import BM25RetrieverHelper
from common_tools.helpers.ressource_helper import Ressource
from common_tools.helpers.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.models.conversation import Conversation
from common_tools.models.question_analysis_base import QuestionAnalysisBase
from common_tools.models.question_rewritting import QuestionRewritting, QuestionRewrittingPydantic
from common_tools.models.question_translation import QuestionTranslation, QuestionTranslationPydantic
from common_tools.rag.rag_inference_pipeline.end_message_ends_pipeline_exception import EndMessageEndsPipelineException
from common_tools.rag.rag_inference_pipeline.greetings_ends_pipeline_exception import GreetingsEndsPipelineException
from common_tools.rag.rag_inference_pipeline.rag_pre_treat_metadata_filters_analysis import RagPreTreatMetadataFiltersAnalysis
from common_tools.rag.rag_service import RagService
from common_tools.workflows.output_name_decorator import output_name
from langchain_core.structured_query import (
    Comparator,
    Comparison,
    Operation,
    Operator,
    StructuredQuery,
    Visitor,
)

class RAGPreTreatment:
    metadata_descriptions = None
    default_filters = {}

    @staticmethod
    def rag_static_pre_treatment(rag:RagService, query:Union[str, Conversation], default_filters:dict = {}) -> tuple[QuestionTranslation, dict]:
        question_analysis, extracted_implicit_metadata, extracted_explicit_metadata = Execute.run_sync_functions_in_parallel_threads(
            (RAGPreTreatment.query_rewritting, (rag, query)),
            (RAGPreTreatment.analyse_query_for_metadata, (rag, query)),
            (RAGPreTreatment.extract_explicit_metadata, (query)),
        )
        
        query_wo_metadata_implicit = extracted_implicit_metadata[0]
        metadata_implicit = extracted_implicit_metadata[1]
        query_wo_metadata_explicit = extracted_explicit_metadata[0]
        metadata_explicit = extracted_explicit_metadata[1]

        merged_metadata = RAGPreTreatment.get_transformed_metadata_and_question_analysis(question_analysis, query_wo_metadata_implicit, metadata_implicit, query_wo_metadata_explicit, metadata_explicit)
        return question_analysis, merged_metadata
    
    @staticmethod
    @output_name('analysed_query')
    def query_standalone_rewritten_from_history(rag:RagService, query:Union[str, Conversation]) -> QuestionRewritting:
        query_standalone_rewritten_prompt = Ressource.load_ressource_file('create_standalone_and_rewritten_query_from_history_prompt.txt')
        query_standalone_rewritten_prompt = RAGPreTreatment._query_rewritting_prompt_replace_all_categories(query_standalone_rewritten_prompt)
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

    #TODO: /!\ WARNING /!\ the query rewritting is domain specific and its prompt too (for studi.com). Thus, it shouldn't be in common_tools
    @staticmethod
    @output_name('analysed_query')
    def query_rewritting(rag:RagService, analysed_query:QuestionRewritting) -> str:        
        query_rewritting_prompt = RAGPreTreatment._query_rewritting_prompt_replace_all_categories(analysed_query.question_with_context)

        response = Execute.get_sync_from_async(Llm.invoke_chain_with_input_async, 'Query rewritting', rag.llm_1, query_rewritting_prompt)
        
        content =  Llm.extract_json_from_llm_response(Llm.get_content(response))
        analysed_query.modified_question = content['modified_question']
        print(f'> Rewritten query: "{analysed_query.modified_question}"')
        return analysed_query

    @staticmethod
    def _query_rewritting_prompt_replace_all_categories(prompt):
        out_dir = "./outputs/" #todo: not generic enough
        diploms_names = ', '.join([f"'{value}'" for value in file.get_as_json(out_dir + 'all/all_diplomas_names.json')])
        certifications_names = ', '.join([f"'{value}'" for value in file.get_as_json(out_dir + 'all/all_certifications_names.json')])
        domains_list = ', '.join([f"'{value}'" for value in file.get_as_json(out_dir + 'all/all_domains_names.json')])
        sub_domains_list = ', '.join([f"'{value}'" for value in file.get_as_json(out_dir + 'all/all_sub_domains_names.json')])

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
    
    @staticmethod
    def analyse_query_for_metadata(rag:RagService, analysed_query:QuestionAnalysisBase) -> tuple[str, Operation]:        
        query = QuestionAnalysisBase.get_modified_question(analysed_query)        
        query_constructor = RagPreTreatMetadataFiltersAnalysis.get_query_constructor_langchain(rag.llm_2, RAGPreTreatment.metadata_descriptions)
        # self_querying_retriever = RagPreTreatMetadataFiltersAnalysis.build_self_querying_retriever_langchain(rag.vectorstore, rag.vector_db_type, rag.llm_2, RAGPreTreatment.metadata_infos, True)
        # query_constructor = self_querying_retriever.query_constructor

        ## WARNING: Not work as async. This is a fix as langchain query contructor (or our async to sync) seems to fails while async with error: Connection error.
        # try:
        #     response_with_filters = Execute.get_sync_from_async(Llm.invoke_chain_with_input_async, 'Analyse metadata', query_constructor, query)
        # except Exception as e:
        #     print(f'+++ Error on "analyse_query_for_metadata": {e}')
        
        response_with_filters = query_constructor.invoke(query)

        metadata_filters = response_with_filters.filter
        return response_with_filters.query, metadata_filters
            
    @staticmethod
    def bypassed_analyse_query_for_metadata(rag:RagService, analysed_query:QuestionAnalysisBase) -> tuple[str, dict]:
        query = QuestionAnalysisBase.get_modified_question(analysed_query)
        return Conversation.get_user_query(query), {}
        
    #OBSOLETE: as it don't take langchain 'Operation' as metadata_filters but a dict (which only works on chroma format of filtering)
    @staticmethod
    def get_transformed_metadata_and_question_analysis(query:Union[str, Conversation], analysed_query :QuestionAnalysisBase, query_wo_metadata_from_implicit:str, implicit_metadata:dict, query_wo_metadata_from_explicit:str = '', explicit_metadata:dict = None) -> dict:
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

        print(f"Extracted metadata filters: '{merged_metadata_filters}'")
        return merged_metadata_filters
    
    @staticmethod
    def metadata_filters_validation_and_correction(query_and_metadata_filters:tuple) -> tuple[str, Operation]:
        """Validate or fix values of metadata filters, like : academic_level, name, domain_name, sub_domain_name, certification_name"""
        query, metadata_filters_to_validate = query_and_metadata_filters
        
        # Translate to chroma DB format for proccessing, then will be re-translated into langchain format 
        metadata_filters_to_validate = RagFilteringMetadataHelper.translate_langchain_metadata_filters_into_chroma_db_format(metadata_filters_to_validate, RAGPreTreatment.metadata_descriptions)

        ### Check for validity of names of metadata filters
        existing_metadata_names = [metadata.name for metadata in RAGPreTreatment.metadata_descriptions]
        metadata_filters_names = RagFilteringMetadataHelper.get_all_filters_keys(metadata_filters_to_validate)
        for metadata_filter_name in metadata_filters_names:
            if metadata_filter_name not in existing_metadata_names:
                RagFilteringMetadataHelper.remove_filter_by_name(metadata_filters_to_validate, metadata_filter_name)
                print(f"/!\\ Filter on invalid metadata name: '{metadata_filter_name}'. It has been removed from metadata filters.")
        
        ### Check for validity of values of metadata filters
 
        #TODO: the following checks are not generic and shouldn't be in common_tools
        metadata_filters_to_validate = RAGPreTreatment.domain_specific_extra_metadata_filters_validation_and_correction(metadata_filters_to_validate)
        
        # Generic check for metadata filters values against possible values defined in the MetadataDescription        
        metadata_filters = RagFilteringMetadataHelper.get_flatten_filters_list(metadata_filters_to_validate)
        for metadata_filter_name, metadata_filter_value in metadata_filters.items():
            corresponding_metadata_info = RAGPreTreatment.metadata_descriptions[existing_metadata_names.index(metadata_filter_name)]
            if corresponding_metadata_info.possible_values:
                if metadata_filter_value not in corresponding_metadata_info.possible_values:
                    retrieved_value, retrieval_score = BM25RetrieverHelper.find_best_match_bm25(corresponding_metadata_info.possible_values, metadata_filter_value)                    
                    if retrieval_score > 0.5:
                        RagFilteringMetadataHelper.update_filter_value(metadata_filters_to_validate, metadata_filter_name, retrieved_value)
                        print(f"/!\\ Filter on metadata '{metadata_filter_name}' with invalid value: '{metadata_filter_value}' was replaced by the nearest match: '{retrieved_value}' with score: [{retrieval_score}].")
                    else:
                        RagFilteringMetadataHelper.remove_filter_by_name(metadata_filters_to_validate, metadata_filter_name)
                        print(f"/!\\ Filter on metadata '{metadata_filter_name}' with invalid value: '{metadata_filter_value}'. It has been removed from metadata filters.")

        print(f"Corrected metadata filters: '{metadata_filters_to_validate}'")
        metadata_filters_to_validate = RagFilteringMetadataHelper.translate_chroma_db_metadata_filters_to_langchain_format(metadata_filters_to_validate)
        return metadata_filters_to_validate

    #TODO: the following checks are not generic and shouldn't be in common_tools
    def domain_specific_extra_metadata_filters_validation_and_correction(metadata_filters_to_validate):
        # Update value of 'academic_level' metadata filter in some cases (like: pre-graduate, BTS, graduate)
        filter_by_academic_level_value = RagFilteringMetadataHelper.find_filter_value(metadata_filters_to_validate, 'academic_level')
        if filter_by_academic_level_value:
            if filter_by_academic_level_value == 'pre-graduate' or filter_by_academic_level_value == 'pré-graduate':
                RagFilteringMetadataHelper.update_filter_value(metadata_filters_to_validate, 'academic_level', 'Bac')
            elif filter_by_academic_level_value == 'BTS':
                RagFilteringMetadataHelper.update_filter_value(metadata_filters_to_validate, 'academic_level', 'Bac+2')
            elif filter_by_academic_level_value == 'graduate':
                RagFilteringMetadataHelper.update_filter_value(metadata_filters_to_validate, 'academic_level', 'Bac+3')

        # Update value of 'name' metadata filter if its value has no perfect match (in all_trainings_names or all_jobs_names)
        filter_by_name_value = RagFilteringMetadataHelper.find_filter_value(metadata_filters_to_validate, 'name')
        if filter_by_name_value:
            all_dir = "./outputs/all/"
            filter_by_type_value = RagFilteringMetadataHelper.find_filter_value(metadata_filters_to_validate, 'type')
            if filter_by_type_value and filter_by_type_value == 'formation':
                all_trainings_names = file.get_as_json(all_dir + 'all_trainings_names') #TODO: single loading
                if filter_by_name_value not in all_trainings_names:
                    retrieved_value, retrieval_score = BM25RetrieverHelper.find_best_match_bm25(all_trainings_names, filter_by_name_value)                    
                    if retrieval_score > 0.5:
                        RagFilteringMetadataHelper.update_filter_value(metadata_filters_to_validate, 'name', retrieved_value)
                        print(f"No match found for metadata value: '{filter_by_name_value}'in all trainings names. Replcaed by the nearest match: '{retrieved_value}' with score of: [{retrieval_score}].")
                    else:
                        RagFilteringMetadataHelper.remove_filter_by_name(metadata_filters_to_validate, 'name')
                        print(f"No match found for metadata value: '{filter_by_name_value}'in all trainings names. Nearest match: '{retrieved_value}' has a low score of: [{retrieval_score}].")
            
            elif filter_by_type_value and filter_by_type_value == 'metier':
                all_trainings_names = file.get_as_json(all_dir + 'all_jobs_names')
                if filter_by_name_value not in all_trainings_names:
                    retrieved_value, retrieval_score = BM25RetrieverHelper.find_best_match_bm25(all_trainings_names, filter_by_name_value)                    
                    if retrieval_score > 0.5:
                        RagFilteringMetadataHelper.update_filter_value(metadata_filters_to_validate, 'name', retrieved_value)
                    else:
                        RagFilteringMetadataHelper.remove_filter_by_name(metadata_filters_to_validate, 'name')
                        print(f"No match found for metadata value: '{filter_by_name_value}'in all trainings names. Nearest match: '{retrieved_value}' has a score of: {retrieval_score}")             

        return metadata_filters_to_validate