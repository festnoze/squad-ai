from collections import defaultdict
from typing import Optional, Union
from common_tools.models.logical_operator import LogicalOperator
from common_tools.models.metadata_description import MetadataDescription
#
from langchain.schema import Document
from langchain_community.query_constructors.chroma import ChromaTranslator
from langchain_community.query_constructors.qdrant import QdrantTranslator
from langchain_community.query_constructors.pinecone import PineconeTranslator
from langchain_core.structured_query import (
    Comparator,
    Comparison,
    Operation,
    Operator,
    StructuredQuery,
    Visitor,
)

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
    def metadata_filtering_predicate_ChromaDb(doc, filters:Union[dict, list], operator=LogicalOperator.AND):
        """Predicate to evaluate filter(s) (handle nested operators)"""
        if filters is None:
            return True
        
        # If filters is a dictionary (single filter or operator like $and/$or)
        if isinstance(filters, dict):
            if "$and" in filters:
                # Recursively handle $and with multiple conditions
                return RagFilteringMetadataHelper.metadata_filtering_predicate_ChromaDb(doc, filters["$and"], LogicalOperator.AND)
            elif "$or" in filters:
                # Recursively handle $or with multiple conditions
                return RagFilteringMetadataHelper.metadata_filtering_predicate_ChromaDb(doc, filters["$or"], LogicalOperator.OR)
            else:
                # Handle single key-value filter (field-value pair)
                return all(doc.metadata.get(key) == value for key, value in filters.items())

        # If filters is a list, apply the operator (AND/OR)
        elif isinstance(filters, list):
            if operator == LogicalOperator.AND:
                return all(
                    RagFilteringMetadataHelper.metadata_filtering_predicate_ChromaDb(doc, sub_filter, LogicalOperator.AND)
                    for sub_filter in filters
                )
            elif operator == LogicalOperator.OR:
                return any(
                    RagFilteringMetadataHelper.metadata_filtering_predicate_ChromaDb(doc, sub_filter, LogicalOperator.OR)
                    for sub_filter in filters
                )
            else:
                raise ValueError(f"Unhandled operator: {operator}")

        return False
    
    @staticmethod
    def translate_langchain_metadata_filters_into_specified_db_type_format(
            langchain_filters: Union[Comparison, Operation],
            metadata_descriptions: list[MetadataDescription] = None,
            vector_db_type: str = "chroma",
            metadata_key: str = "metadata"
        ) -> dict:
        """
        Translate LangChain-style filters into vector database-specific filter formats.

        :param langchain_filters: The LangChain-style filter object (Comparison or Operation).
        :param metadata_descriptions: Optional list of metadata descriptions to validate filter attributes.
        :param vector_db_type: The target database translator type (e.g., "chroma", "qdrant", "pinecone").
        :param metadata_key: The key under which metadata is stored (used by QdrantTranslator).
        :return: A dictionary representing the translated filter for the specified database.
        """
        if langchain_filters is None:
            return None
        
        # Initialize the appropriate translator based on the specified type
        translator:Visitor = None
        if vector_db_type == "chroma":
            translator = ChromaTranslator()
        elif vector_db_type == "qdrant":
            translator = QdrantTranslator(metadata_key=metadata_key)
        elif vector_db_type == "pinecone":
            translator = PineconeTranslator()
        else:
            raise ValueError(f"Unsupported translator type: {vector_db_type}")

        # Validate the filter attributes against provided metadata descriptions
        valid_metadata_keys = set(metadata_description.name if hasattr(metadata_description, 'name') else metadata_description['name'] for metadata_description in metadata_descriptions) if metadata_descriptions else set()

        def validate_and_translate(filter_obj):
            if isinstance(filter_obj, Operation):
                # Recursively process operations
                translated_args = [
                    validate_and_translate(arg) for arg in filter_obj.arguments
                ]
                # Filter out None values resulting from invalid attributes
                translated_args = [arg for arg in translated_args if arg is not None]
                if not translated_args:
                    return None
                return Operation(operator=filter_obj.operator, arguments=translated_args)
            elif isinstance(filter_obj, Comparison):
                # Check if the attribute is valid
                if not valid_metadata_keys or filter_obj.attribute in valid_metadata_keys:
                    return filter_obj
                else:
                    print(f"Warning: Attribute '{filter_obj.attribute}' is not recognized.")
                    return None
            else:
                raise ValueError(f"Unsupported filter type: {type(filter_obj)}")

        # Validate and translate the filters
        validated_filters = validate_and_translate(langchain_filters)
        if validated_filters is None:
            return {}

        # Use the translator to convert the validated filters into the target format
        translated_filter = translator.visit_operation(validated_filters)
        return translated_filter
    
    @staticmethod
    def translate_langchain_metadata_filters_into_chroma_db_format(langchain_filters: Union[Comparison, Operation], metadata_infos: list[MetadataDescription] = None) -> dict:
        if langchain_filters is None:
            return None
        
        filters = []
        valid_keys = set(attr_info.name for attr_info in metadata_infos) if metadata_infos else set()
        operator = None
        filter_dict = {}

        if langchain_filters is not None:            
            if isinstance(langchain_filters, Operation):
                filters = [
                    RagFilteringMetadataHelper.translate_langchain_metadata_filters_into_chroma_db_format(sub_filter, metadata_infos) 
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
    def translate_chroma_db_metadata_filters_to_langchain_format(chroma_filters: dict) -> Operation: #Union[Operation, Comparison, None]:
        """
        Translate ChromaDB filter format back into LangChain-style Operations or Comparisons.

        :param chroma_filters: The filter dictionary in ChromaDB format.
        :return: A LangChain Operation or Comparison object.
        """
        def parse_filter(filters):
            if not isinstance(filters, dict):
                return None

            # Logical operators mapping
            for operator_key in ["$and", "$or", "$not"]:
                if operator_key in filters:
                    operator = operator_key.strip("$")
                    sub_filters = filters[operator_key]

                    # Recursively parse the sub-filters
                    parsed_arguments = [parse_filter(sub_filter) for sub_filter in sub_filters]
                    parsed_arguments = [arg for arg in parsed_arguments if arg is not None]

                    # Handle 'not' as a special case (1 argument only)
                    if operator == "not" and len(parsed_arguments) == 1:
                        return Operation(operator=operator, arguments=parsed_arguments)

                    # For 'and' and 'or'
                    return Operation(operator=operator, arguments=parsed_arguments)

            # Base case: A single attribute-value pair (Comparison)
            for key, value in filters.items():
                if not key.startswith("$"):  # Skip reserved keys like "$and", "$or", "$not"
                    return Comparison(attribute=key, comparator="eq", value=value)

            return None
        
        if chroma_filters is None:
            return None
        else:
            return parse_filter(chroma_filters)
   
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
    def remove_filter_by_name(metadata: Union[dict, list], key: str) -> Union[dict, list, None]:
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
                new_value = RagFilteringMetadataHelper.remove_filter_by_name(v, key)
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
                updated_item = RagFilteringMetadataHelper.remove_filter_by_name(item, key)
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
    
    @staticmethod
    def get_all_filters_keys(metadata: Union[dict, list]) -> list:
        """
        Parse all provided filters and return a list of all distinct filter keys,
        excluding logical operators ($and, $or, $not) and comparison operators ($eq, $ne, $lt, $gt, etc.).

        :param metadata: The metadata containing filters (can be a dict or list).
        :return: A list of distinct filter keys.
        """
        keys = set()

        def extract_keys(item):
            if isinstance(item, dict):
                for key, value in item.items():
                    # Exclude logical and comparison operators
                    if key not in {"$and", "$or", "$not", "$eq", "$ne", "$lt", "$lte", "$gt", "$gte", "$in", "$nin"}:
                        keys.add(key)
                    if isinstance(value, (dict, list)):
                        extract_keys(value)

            elif isinstance(item, list):
                for sub_item in item:
                    extract_keys(sub_item)

        extract_keys(metadata)
        return list(keys)

    
    @staticmethod
    def get_flatten_filters_list(metadata: Union[dict, list]) -> dict:
        """
        Flatten filters into a key-value JSON object, removing '$and', '$or', and '$not' logical operators.

        :param metadata: The metadata containing filters (can be a dict or list).
        :return: A flattened JSON object with key-value pairs.
        """
        flattened_filters = {}

        def extract_kv(item):
            if isinstance(item, dict):
                for key, value in item.items():
                    if key in {"$and", "$or", "$not"}:
                        # Skip logical operators but process their contents
                        if isinstance(value, list):
                            for sub_item in value:
                                extract_kv(sub_item)
                        elif isinstance(value, dict):
                            extract_kv(value)
                    else:
                        # Add key-value pairs directly or process nested structures
                        if isinstance(value, (dict, list)):
                            extract_kv(value)
                        else:
                            flattened_filters[key] = value
            elif isinstance(item, list):
                for sub_item in item:
                    extract_kv(sub_item)

        extract_kv(metadata)
        return flattened_filters
    
         
    @staticmethod
    def auto_generate_metadata_descriptions_from_docs_metadata(documents: list[Document], max_values: int = 10, metadata_keys_description:dict = None) -> list[MetadataDescription]:
        metadata_field_info = []
        value_counts = defaultdict(list)

        for doc in documents:
            for key, value in doc.metadata.items():
                if value not in value_counts[key]:
                    value_counts[key].append(value)

        for key, possible_values in value_counts.items():
            description = f"'{key}' metadata"
            if metadata_keys_description and key in metadata_keys_description:
                description += f" (indicate: {metadata_keys_description[key]})"
            value_type = type(possible_values[0]).__name__
            if len(possible_values) <= max_values:
                values_str = ', '.join([f"'{value}'" for value in possible_values])
                description += f". One value in: [{values_str}]"
            
            metadata_field_info.append(MetadataDescription(name=key, description=description, type=value_type, possible_values=possible_values))

        return metadata_field_info