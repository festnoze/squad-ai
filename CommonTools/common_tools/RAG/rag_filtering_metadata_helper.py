from typing import Optional, Union
from common_tools.models.logical_operator import LogicalOperator
from langchain.chains.query_constructor.base import AttributeInfo

from langchain_core.structured_query import Comparison, Operation

class RagFilteringMetadataHelper:
    
    @staticmethod
    def has_manual_filters(question: str) -> bool:
        return  question.__contains__("filters:") or question.__contains__("filtres :")
    
    @staticmethod
    def extract_manual_filters(query: str) -> tuple[dict, str]:
        filters = {}
        if query.__contains__("filters:"):
            filters_str = query.split("filters:")[1]
            query_wo_metadata = query.split("filters:")[0]
        elif query.__contains__("filtres :"):
            filters_str = query.split("filtres :")[1]
            query_wo_metadata = query.split("filtres :")[0]
        filters_str = filters_str.strip()
        filters = RagFilteringMetadataHelper.get_filters_from_str(filters_str)
        return filters, query_wo_metadata
    
    #todo: make it generic from the metadat infos
    @staticmethod
    def get_filters_from_str(filters_str: str) -> dict:
        filters = []
        filters_list = filters_str.lower().split(',')

        for filter in filters_list:
            # functional_type: Controller, Service, Repository, ...
            if "controller" in filter or "service" in filter or "repository" in filter:
                # Ensure the first letter is uppercase
                functional_type = filter.strip().capitalize()
                filters.append({"functional_type": functional_type})
            # summary_kind: class, method, (property, enum_member), ...
            elif "method" in filter or "méthode" in filter:
                filters.append({"summary_kind": "method"})
            elif "class" in filter:
                filters.append({"summary_kind": "class"})

        # If there are more than one filters, wrap in "$and", otherwise return a single filter
        if len(filters) > 1:
            return {"$and": filters}
        elif len(filters) == 1:
            return filters[0]  # Just return the single condition directly
        else:
            return {}  # Return an empty filter if no conditions found
        
    @staticmethod
    def filters_predicate(doc, filters:Union[dict, list], operator=LogicalOperator.AND):
        """Predicate to evaluate filter(s) (handle nested operators)"""

        # If filters is a dictionary (single filter or operator like $and/$or)
        if isinstance(filters, dict):
            if "$and" in filters:
                # Recursively handle $and with multiple conditions
                return RagFilteringMetadataHelper.filters_predicate(doc, filters["$and"], LogicalOperator.AND)
            elif "$or" in filters:
                # Recursively handle $or with multiple conditions
                return RagFilteringMetadataHelper.filters_predicate(doc, filters["$or"], LogicalOperator.OR)
            else:
                # Handle single key-value filter (field-value pair)
                return all(doc.metadata.get(key) == value for key, value in filters.items())

        # If filters is a list, apply the operator (AND/OR)
        elif isinstance(filters, list):
            if operator == LogicalOperator.AND:
                return all(
                    RagFilteringMetadataHelper.filters_predicate(doc, sub_filter, LogicalOperator.AND)
                    for sub_filter in filters
                )
            elif operator == LogicalOperator.OR:
                return any(
                    RagFilteringMetadataHelper.filters_predicate(doc, sub_filter, LogicalOperator.OR)
                    for sub_filter in filters
                )
            else:
                raise ValueError(f"Unhandled operator: {operator}")

        return False
    
    @staticmethod
    def get_filters_from_comparison(langchain_filters: Union[Comparison, Operation], metadata_infos: list[AttributeInfo] = None) -> dict:
        filters = []
        valid_keys = set(attr_info.name for attr_info in metadata_infos) if metadata_infos else set()
        operator = None
        filter_dict = {}

        if langchain_filters is not None:            
            if isinstance(langchain_filters, Operation):
                filters = [
                    RagFilteringMetadataHelper.get_filters_from_comparison(sub_filter, metadata_infos) 
                    for sub_filter in langchain_filters.arguments
                ]
                filters = [f for f in filters if f and f != "NO_FILTER"]
                operator = langchain_filters.operator.value
            elif isinstance(langchain_filters, Comparison):
                # Add filter only if the attribute is in valid_keys or if no valid_keys are provided
                if not valid_keys or langchain_filters.attribute in valid_keys:
                    if langchain_filters.value != "NO_FILTER":
                        filter_dict = {langchain_filters.attribute: langchain_filters.value}
                        filters.append(filter_dict)
            else:
                raise ValueError(f"Unsupported filter type: {type(langchain_filters)}")

        # Combine filters using logical operators if needed
        if len(filters) > 1:
            return {f"${operator if operator else 'and'}": filters}
        elif len(filters) == 1:
            return filters[0]
        else:
            return {}

    @staticmethod
    def does_contain_filter(metadata: Union[dict, list], key: str, value: str = None) -> bool:
        """Check if a key-value pair exists in the metadata, including logical operators."""
        if isinstance(metadata, dict):
            # Handle logical operators like $and, $or, $not
            if "$and" in metadata:
                return any(RagFilteringMetadataHelper.does_contain_filter(sub_filter, key, value) for sub_filter in metadata["$and"])
            elif "$or" in metadata:
                return any(RagFilteringMetadataHelper.does_contain_filter(sub_filter, key, value) for sub_filter in metadata["$or"])
            elif "$not" in metadata:
                return not RagFilteringMetadataHelper.does_contain_filter(metadata["$not"], key, value)
            
            # Check if the current dictionary contains the key-value pair
            if key in metadata and (value is None or metadata[key] == value):
                return True

            # Recursively check nested dictionaries
            return any(RagFilteringMetadataHelper.does_contain_filter(v, key, value) for v in metadata.values())

        elif isinstance(metadata, list):
            # Check each item in the list
            return any(RagFilteringMetadataHelper.does_contain_filter(item, key, value) for item in metadata)

        # If it's not a dict or list, return False
        return False
