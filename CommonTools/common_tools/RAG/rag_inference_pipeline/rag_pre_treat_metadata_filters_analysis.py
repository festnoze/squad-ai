from collections import defaultdict
import json
from typing import Optional, Union
from langchain_community.query_constructors.chroma import ChromaTranslator
from langchain_community.query_constructors.qdrant import QdrantTranslator
from langchain.retrievers.self_query.base import SelfQueryRetriever
from langchain.chains.query_constructor.base import StructuredQueryOutputParser, get_query_constructor_prompt
from langchain_core.documents import Document
from langchain.chains.query_constructor.base import AttributeInfo
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
#
from common_tools.models.metadata_description import MetadataDescription

class RagPreTreatMetadataFiltersAnalysis:
    #todo: move to inference pipeline?
    def build_self_querying_retriever_langchain(self, llm, metadata_description: list[MetadataDescription] = None, get_query_constructor:bool = True) -> tuple :
        document_description = "Description of the document"
        if not metadata_description:
            metadata_description = RagPreTreatMetadataFiltersAnalysis._auto_generate_metadata_infos_from_docs_metadata(self.langchain_documents)

        if get_query_constructor:
            # Get query translator adapted to the vectorstore type
            if self.vector_db_type == "qdrant":
                translator = QdrantTranslator('')
            elif self.vector_db_type == "chroma":
                translator = ChromaTranslator()
            else:
                raise ValueError(f"Unsupported vectorstore type: {self.vector_db_type}")
            
            query_constructor = self.get_query_constructor_langchain(llm, metadata_description)
            self_querying_retriever = SelfQueryRetriever(
                                            query_constructor=query_constructor,
                                            vectorstore=self.vectorstore,
                                            structured_query_translator=translator)
            
            return self_querying_retriever, query_constructor
        else:
            self_querying_retriever = SelfQueryRetriever.from_llm(
                                            llm, #choose the best llm for the job
                                            self.vectorstore,
                                            document_description,
                                            metadata_description)
            return self_querying_retriever, None

    def get_query_constructor_langchain(llm, metadata_descriptions: list[MetadataDescription] = None):
        document_description = "Description of the document"
        metadata_descriptions_pydantic = [metadata_description.to_pydantic() for metadata_description in metadata_descriptions]
        prompt = get_query_constructor_prompt(
                    document_description,
                    metadata_descriptions_pydantic,
                )
        output_parser = StructuredQueryOutputParser.from_components()
        query_constructor = prompt | llm | output_parser
        return query_constructor
    
    def get_query_constructor_custom(llm, metadata_descriptions: list[MetadataDescription] = None):
        document_description = "Description of the document"
        metadata_descriptions_pydantic = [metadata_description.to_pydantic() for metadata_description in metadata_descriptions]
        prompt = RagPreTreatMetadataFiltersAnalysis.get_query_constructor_prompt_custom(document_description, metadata_descriptions_pydantic)
        output_parser = StructuredQueryOutputParser.from_components()
        promptlate = ChatPromptTemplate.from_template(prompt)
        query_constructor = prompt | llm | output_parser | RunnablePassthrough()
        return query_constructor    
        
    @staticmethod
    def _auto_generate_metadata_infos_from_docs_metadata(documents: list[Document], max_values: int = 10, metadata_keys_description:dict = None) -> list[MetadataDescription]:
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
    
    def get_query_constructor_prompt_custom(
            document_description: str,
            metadata_descriptions: Union[list[MetadataDescription], list[AttributeInfo]],
            examples: Optional[list[dict]] = None
        ) -> str:
        """
        Generates a prompt for the LLM to parse user queries into structured filters.

        Args:
            document_description: A description of the document.
            metadata_descriptions: A list of MetadataDescription objects.
            examples: Optional list of examples to include in the prompt.

        Returns:
            A string containing the generated prompt.
        """
        # Convert metadata descriptions to a JSON-like structure
        attributes = {}
        for meta in metadata_descriptions:
            attr = {
                "description": meta.description,
                "type": meta.type
            }

        data_source = {
            "content": document_description,
            "attributes": attributes
        }

        # Convert data source to a JSON string with ensure_ascii=False
        data_source_str = json.dumps(data_source, ensure_ascii=False, indent=4)

        # Assemble the prompt
        prompt = (
            "Your goal is to analyze the user's query and extract filters based on the metadata attributes provided.\n\n"
            "<< Data Source >>\n"
            f"```json\n{data_source_str}\n```\n\n"
            "When responding, use the following JSON schema:\n"
            "```json\n"
            "{\n"
            '    "query": string,  // The text to search within the document contents.\n'
            '    "filter": string  // The logical condition for filtering documents.\n'
            "}\n"
            "```\n"
            "The filter should be a logical expression using the comparators and operators:\n"
            "- Comparators: eq | ne | gt | gte | lt | lte | contain | like | in | nin\n"
            "- Logical Operators: and | or | not\n"
            "Use only the attributes provided in the data source.\n"
            "Ensure that the filter expressions are valid and consider the possible values of each attribute.\n\n"
        )

        # Add examples if provided
        if examples:
            prompt += "<< Examples >>\n"
            for idx, example in enumerate(examples, start=1):
                prompt += f"Example {idx}:\n"
                prompt += f"User Query:\n{example['user_query']}\n\n"
                prompt += "Structured Request:\n"
                prompt += f"```json\n{json.dumps(example['structured_request'], ensure_ascii=False, indent=4)}\n```\n\n"

        # Add placeholder for the user's query
        prompt += "User Query:\n{query}\n\n"
        prompt += "Structured Request:\n"

        return prompt

        