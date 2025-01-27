from typing import Union
#
from langchain_core.structured_query import (
    Comparison,
    Operation,
    Operator,
)
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.rag_filtering_metadata_helper import RagFilteringMetadataHelper
from common_tools.helpers.rag_bm25_retriever_helper import BM25RetrieverHelper

class StudiPublicWebsiteRagSpecificConfig:
    @staticmethod
    async def get_domain_specific_metadata_filters_validation_and_correction_async_method(langchain_filters: Union[Operation, Comparison]) -> Union[Operation, Comparison, None]:
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
    
    @staticmethod
    def get_domain_specific_default_filters() -> dict:
        return {}
    
