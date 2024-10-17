from typing import Optional, Union
from common_tools.models.logical_operator import LogicalOperator
from langchain.chains.query_constructor.base import AttributeInfo

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
    
    from langchain_core.structured_query import Comparison

    @staticmethod
    def get_filters_from_comparison(comparison: Comparison, metadata_infos: list[AttributeInfo] = None) -> dict:
        filters = []
        valid_keys = set(attr_info.name for attr_info in metadata_infos) if metadata_infos else None
        filter_dict = {}
        if comparison is not None:
            filter_dict = { comparison.attribute: comparison.value}

        if not valid_keys:
            filters.append(filter_dict)
        else:
            if comparison.attribute in valid_keys:
                filters.append(filter_dict)            

        if len(filters) > 1:
            return {"$and": filters}
        elif len(filters) == 1:
            return filters[0]
        else:
            return {}


