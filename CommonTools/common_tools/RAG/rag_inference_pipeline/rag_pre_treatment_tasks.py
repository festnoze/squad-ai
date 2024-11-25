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
from common_tools.workflows.workflow_output_decorator import workflow_output
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
        question_analysis, extracted_implicit_metadata, extracted_explicit_metadata = Execute.run_several_functions_as_concurrent_async_tasks(
            (RAGPreTreatment.query_rewritting_async, (rag, query)),
            (RAGPreTreatment.analyse_query_for_metadata_async, (rag, query)),
            (RAGPreTreatment.extract_explicit_metadata, (query)),
        )
        
        query_wo_metadata_implicit = extracted_implicit_metadata[0]
        metadata_implicit = extracted_implicit_metadata[1]
        query_wo_metadata_explicit = extracted_explicit_metadata[0]
        metadata_explicit = extracted_explicit_metadata[1]

        merged_metadata = RAGPreTreatment.get_transformed_metadata_and_question_analysis(question_analysis, query_wo_metadata_implicit, metadata_implicit, query_wo_metadata_explicit, metadata_explicit)
        return question_analysis, merged_metadata
    
    @staticmethod
    @workflow_output('analysed_query')
    async def query_standalone_rewritten_from_history_async(rag:RagService, query:Union[str, Conversation]) -> QuestionRewritting:
        query_standalone_rewritten_prompt = Ressource.load_ressource_file('create_standalone_and_rewritten_query_from_history_prompt.txt')
        query_standalone_rewritten_prompt = RAGPreTreatment._query_rewritting_prompt_replace_all_categories(query_standalone_rewritten_prompt)
        query_standalone_rewritten_prompt = RAGPreTreatment._replace_query_and_history_in_prompt(query, query_standalone_rewritten_prompt)  
                
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
                        query_standalone_rewritten_prompt, QuestionRewrittingPydantic, QuestionRewritting)

        response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
                'Standalone and rewritten query', [rag.llm_2, rag.llm_3], output_parser, 10, *[prompt_for_output_parser])
        
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
    @workflow_output('analysed_query')
    async def query_standalone_from_history_async(rag:RagService, query:Union[str, Conversation]) -> QuestionRewritting:
        query_standalone_prompt = Ressource.get_create_standalone_query_from_history_prompt()
        user_query = Conversation.get_user_query(query)
        query_standalone_prompt = query_standalone_prompt.replace('{user_query}', user_query)
        query_standalone_prompt = query_standalone_prompt.replace('{conversation_history}', Conversation.conversation_history_as_str(query, include_current_user_query=False))

        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            query_standalone_prompt, QuestionRewrittingPydantic, QuestionRewritting
        )

        response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
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
    @workflow_output('analysed_query')
    async def query_rewritting_async(rag:RagService, analysed_query:QuestionRewritting) -> str:        
        query_rewritting_prompt = RAGPreTreatment._query_rewritting_prompt_replace_all_categories(analysed_query.question_with_context)

        response = await Llm.invoke_chain_with_input_async('Query rewritting', rag.llm_1, query_rewritting_prompt)
        
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
    @workflow_output('analysed_query')
    async def query_translation_async(rag:RagService, query:Union[str, Conversation]) -> QuestionTranslation:
        user_query = Conversation.get_user_query(query)
        prefilter_prompt = Ressource.get_language_detection_prompt()
        prefilter_prompt = prefilter_prompt.replace("{question}", user_query)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            prefilter_prompt, QuestionTranslationPydantic, QuestionTranslation
        )
        response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
            'query_translation', [rag.llm_1, rag.llm_2, rag.llm_3], output_parser, 10, *[prompt_for_output_parser]
        )
        question_analysis = response[0]
        question_analysis['question'] = user_query
        if question_analysis['detected_language'].__contains__('english'):
            question_analysis['translated_question'] = user_query
        return QuestionTranslation(**question_analysis)

    @staticmethod    
    @workflow_output('analysed_query') #todo: to replace with above
    async def bypassed_query_translation_async(rag:RagService, query:Union[str, Conversation]) -> QuestionTranslation:
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
    async def analyse_query_for_metadata_async(rag:RagService, analysed_query:QuestionAnalysisBase) -> tuple[str, Operation]:        
        query = QuestionAnalysisBase.get_modified_question(analysed_query)        
        query_constructor = RagPreTreatMetadataFiltersAnalysis.get_query_constructor_langchain(rag.llm_2, RAGPreTreatment.metadata_descriptions)
        # self_querying_retriever = RagPreTreatMetadataFiltersAnalysis.build_self_querying_retriever_langchain(rag.vectorstore, rag.vector_db_type, rag.llm_2, RAGPreTreatment.metadata_infos, True)
        # query_constructor = self_querying_retriever.query_constructor

        ## WARNING: Not work as async. This is a fix as langchain query contructor (or our async to sync) seems to fails while async with error: Connection error.
        # try:
        #     response_with_filters = Execute.async_wrapper_to_sync(Llm.invoke_chain_with_input_async, 'Analyse metadata', query_constructor, query)
        # except Exception as e:
        #     print(f'+++ Error on "analyse_query_for_metadata": {e}')
        
        response_with_filters = await query_constructor.ainvoke(query)

        metadata_filters = response_with_filters.filter
        return response_with_filters.query, metadata_filters
            
    @staticmethod
    def bypassed_analyse_query_for_metadata(rag:RagService, analysed_query:QuestionAnalysisBase) -> tuple[str, dict]:
        query = QuestionAnalysisBase.get_modified_question(analysed_query)
        return Conversation.get_user_query(query), {}
            
    #TODO: the param shouldn't be a tuple but the two params directly if flatten tuple works as intended
    @staticmethod
    async def metadata_filters_validation_and_correction_async(query_and_metadata_filters:tuple) -> tuple[str, Operation]:
        """Validate or fix values of metadata filters, like : academic_level, name, domain_name, sub_domain_name, certification_name"""
        #TODO: the following tuple flattening should not be done by the method itself but by the flatten_tuples methods
        query, metadata_filters_to_validate = query_and_metadata_filters

        # Domain specific extra validity check of metadata filters
        #TODO: the following checks are not generic and shouldn't be in common_tools
        metadata_filters_to_validate = await RAGPreTreatment.domain_specific_metadata_filters_validation_and_correction_async(metadata_filters_to_validate)
                
        # Generic validity check of metadata filters keys or values, and remove filters with invalid ones
        await RagFilteringMetadataHelper.validate_langchain_metadata_filters_against_metadata_descriptions_async(metadata_filters_to_validate, RAGPreTreatment.metadata_descriptions, does_throw_error_upon_failure= False)
      
        print(f"Corrected metadata filters: '{str(metadata_filters_to_validate)}'")
        return metadata_filters_to_validate

    #TODO: the following checks are not generic and shouldn't be in common_tools
    @staticmethod
    async def domain_specific_metadata_filters_validation_and_correction_async(langchain_filters: Union[Operation, Comparison]) -> Union[Operation, Comparison, None]:
        """
        Perform domain-specific validation and correction on LangChain filters (Operation or Comparison).

        :param langchain_filters: The LangChain-style filter object (Operation or Comparison).
        :return: The validated and corrected filter object, or None if all filters are invalid.
        """
        async def validate_and_correct_async(filter_obj):
            if filter_obj is None:
                return None
            elif isinstance(filter_obj, Comparison):
                # Academic level corrections
                if filter_obj.attribute == "academic_level":
                    if filter_obj.value in ["pre-graduate", "pré-graduate"]:
                        return Comparison(attribute=filter_obj.attribute, comparator=filter_obj.comparator, value="Bac")
                    elif filter_obj.value == "BTS":
                        return Comparison(attribute=filter_obj.attribute, comparator=filter_obj.comparator, value="Bac+2")
                    elif filter_obj.value == "graduate":
                        return Comparison(attribute=filter_obj.attribute, comparator=filter_obj.comparator, value="Bac+3")
                
                # Name corrections based on type (formation or métier)
                elif filter_obj.attribute == "name":
                    # Load type filter value
                    type_filter = RagFilteringMetadataHelper.find_filter_value(langchain_filters, "type")
                    filter_by_type_value = type_filter.value if type_filter else None

                    all_dir = "./outputs/all/"
                    if filter_by_type_value == "formation":
                        all_trainings_names = file.get_as_json(all_dir + "all_trainings_names")
                        if filter_obj.value not in all_trainings_names:
                            retrieved_value, retrieval_score = await BM25RetrieverHelper.find_best_match_bm25_async(all_trainings_names, filter_obj.value)
                            if retrieval_score > 0.5:
                                print(
                                    f"No match found for metadata value: '{filter_obj.value}' in all trainings names. "
                                    f"Replaced by the nearest match: '{retrieved_value}' with score: [{retrieval_score}]."
                                )
                                return Comparison(attribute=filter_obj.attribute, comparator=filter_obj.comparator, value=retrieved_value)
                            else:
                                print(
                                    f"No match found for metadata value: '{filter_obj.value}' in all trainings names. "
                                    f"Nearest match: '{retrieved_value}' has a low score: [{retrieval_score}]. Filter removed."
                                )
                                return None
                    elif filter_by_type_value == "metier":
                        all_jobs_names = file.get_as_json(all_dir + "all_jobs_names")
                        if filter_obj.value not in all_jobs_names:
                            retrieved_value, retrieval_score = await BM25RetrieverHelper.find_best_match_bm25_async(all_jobs_names, filter_obj.value)
                            if retrieval_score > 0.5:
                                print(
                                    f"No match found for metadata value: '{filter_obj.value}' in all jobs names. "
                                    f"Replaced by the nearest match: '{retrieved_value}' with score: [{retrieval_score}]."
                                )
                                return Comparison(attribute=filter_obj.attribute, comparator=filter_obj.comparator, value=retrieved_value)
                            else:
                                print(
                                    f"No match found for metadata value: '{filter_obj.value}' in all jobs names. "
                                    f"Nearest match: '{retrieved_value}' has a low score: [{retrieval_score}]. Filter removed."
                                )
                                return None

                # Return unchanged Comparison if no corrections were needed
                return filter_obj

            elif isinstance(filter_obj, Operation):
                # Recursively validate and correct arguments
                validated_arguments = [
                    await validate_and_correct_async(arg) for arg in filter_obj.arguments
                ]
                # Remove None values (invalid filters)
                validated_arguments = [arg for arg in validated_arguments if arg is not None]

                # If no arguments remain valid, return None
                if not validated_arguments:
                    return None

                # Return the corrected Operation
                return Operation(operator=filter_obj.operator, arguments=validated_arguments)

            else:
                raise ValueError(f"Unsupported filter type: {type(filter_obj)}")

        # Start validation and correction
        return await validate_and_correct_async(langchain_filters)