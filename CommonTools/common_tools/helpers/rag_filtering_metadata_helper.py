from typing import Optional, Union
from common_tools.models.logical_operator import LogicalOperator
from langchain_core.structured_query import Comparison, Operation
from common_tools.models.metadata_description import MetadataDescription

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
    
    #TODO: make it generic from the metadata infos
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
    def get_filters_from_comparison(langchain_filters: Union[Comparison, Operation], metadata_infos: list[MetadataDescription] = None) -> dict:
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
    def find_filter_value(metadata: Union[dict, list], key: str, value: str = None) -> any:
        """
        Search for a key-value pair in the metadata and return the associated value if found.
        Mimics `does_contain_filter` but returns the value or `None` if not found.
        """
        if isinstance(metadata, dict):
            # Handle logical operators like $and, $or, $not
            if "$and" in metadata:
                for sub_filter in metadata["$and"]:
                    result = RagFilteringMetadataHelper.find_filter_value(sub_filter, key, value)
                    if result is not None:
                        return result
            elif "$or" in metadata:
                for sub_filter in metadata["$or"]:
                    result = RagFilteringMetadataHelper.find_filter_value(sub_filter, key, value)
                    if result is not None:
                        return result
            elif "$not" in metadata:
                result = RagFilteringMetadataHelper.find_filter_value(metadata["$not"], key, value)
                return None if result is not None else None

            # Check if the current dictionary contains the key-value pair
            if key in metadata and (value is None or metadata[key] == value):
                return metadata[key]

            # Recursively check nested dictionaries
            for v in metadata.values():
                result = RagFilteringMetadataHelper.find_filter_value(v, key, value)
                if result is not None:
                    return result

        elif isinstance(metadata, list):
            # Check each item in the list
            for item in metadata:
                result = RagFilteringMetadataHelper.find_filter_value(item, key, value)
                if result is not None:
                    return result      
                 
        return None # If it's not a dict or list, return None

    @staticmethod
    def does_contain_filter(metadata: Union[dict, list], key: str, value: str = None) -> bool:
        """Check if a key-value pair exists in the metadata, including logical operators."""
        return RagFilteringMetadataHelper.find_filter_value(metadata, key, value) is not None
    
    @staticmethod
    def remove_filter_key(metadata: Union[dict, list], key: str) -> Union[dict, list, None]:
        """
        Recursively removes all occurrences of the specified key from the filter metadata.
        If a parent container (dict or list) becomes empty as a result, it is also removed.
        
        Parameters:
        - metadata: The filter structure (dict or list).
        - key: The key to be removed.

        Returns:
        - The modified metadata with the key removed.
        - None if the container becomes empty.
        """
        if isinstance(metadata, dict):
            # Remove the key if it exists in the current dictionary
            if key in metadata:
                del metadata[key]
            
            # Recursively process each value in the dictionary
            keys_to_delete = []
            for k, v in metadata.items():
                new_value = RagFilteringMetadataHelper.remove_filter_key(v, key)
                if new_value is None:  # Mark empty containers for deletion
                    keys_to_delete.append(k)
                else:
                    metadata[k] = new_value
            
            # Delete empty containers
            for k in keys_to_delete:
                del metadata[k]

            # Return None if the dictionary is now empty
            return metadata if metadata else None

        elif isinstance(metadata, list):
            # Recursively process each item in the list
            new_list = []
            for item in metadata:
                updated_item = RagFilteringMetadataHelper.remove_filter_key(item, key)
                if updated_item is not None:  # Keep non-empty items
                    new_list.append(updated_item)

            # Return the modified list, or None if it is empty
            return new_list if new_list else None

        # Return the metadata itself if it's not a dict or list
        return metadata

    @staticmethod
    def update_filter_value(metadata: Union[dict, list], key: str, new_value: any) -> Union[dict, list, None]:
        """
        Recursively updates all occurrences of the specified key with the provided value
        in the filter metadata.

        Parameters:
        - metadata: The filter structure (dict or list).
        - key: The key whose value needs to be updated.
        - new_value: The new value to assign to the key.

        Returns:
        - The modified metadata with the updated values.
        """
        if isinstance(metadata, dict):
            # Update the key if it exists in the current dictionary
            if key in metadata:
                metadata[key] = new_value
            
            # Recursively process each value in the dictionary
            for k, v in metadata.items():
                metadata[k] = RagFilteringMetadataHelper.update_filter_value(v, key, new_value)

            return metadata

        elif isinstance(metadata, list):
            # Recursively process each item in the list
            return [
                RagFilteringMetadataHelper.update_filter_value(item, key, new_value)
                for item in metadata
            ]

        # Return the metadata itself if it's not a dict or list
        return metadata