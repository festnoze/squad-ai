from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import requests
from langchain_community.retrievers import BM25Retriever
from rank_bm25 import BM25Okapi
from langchain.docstore.document import Document
import numpy as np
#
from common_tools.helpers import txt

class DrupalJsonApiClient:
    def __init__(self, base_url):
        if base_url:
            self.base_url = base_url
        else:
            raise ValueError("Base URL is required to initialize the DrupalJsonApiClient")

    def _perform_request(self, endpoint, remaining_retries=5, allowed_retries=5):
        """
        Makes a GET request to the specified JSON:API endpoint.
        
        :param endpoint: The JSON:API item (e.g. 'node/article' for: /jsonapi/node/article)
        :return: The JSON response or an error message if the request fails
        """
        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
            return response.json()  # Return the JSON response if the request is successful
        except requests.RequestException as e:
            print(f"Error fetching data from {url}: {e}")
            if remaining_retries > 0: # Retry 'allowed_retries' times upon request failure
                remaining_retries = remaining_retries - 1
                time.sleep((allowed_retries-remaining_retries) * 3)
                return self._perform_request(endpoint, remaining_retries=remaining_retries, allowed_retries=allowed_retries)
            raise e

    # def get_articles_filter_status_1(self):
    #     return self._perform_request('article?filter[status]=1')

    # def get_article_include_uid(self):
    #     return self._perform_request('article?include=uid')

    # def get_article_page_limit__5_page_offset__0(self):
    #     return self._perform_request('article?page[limit]=5&page[offset]=0')

    # def get_article_sort_created(self):
    #     return self._perform_request('article?sort=created')

    
    def extract_common_data_from_nodes(self, nodes:list, included_relationships=[], included_relationships_ids=[]):
        items = []
        for i, source_node in enumerate(nodes):
            target_node ={
                'id': source_node['id'],
                'type': source_node['type']
            }
            if not 'attributes' in source_node:
                continue

            self.set_attribut_value_from_source(target_node, source_node, 'title')
            self.set_attribut_value_from_source(target_node, source_node, 'name')
            self.set_attribut_value_from_source(target_node, source_node, 'description')

            if 'links' in source_node and 'related' in source_node['links']:
                target_node['related_url'] = source_node['links']['related']['href']
            if 'changed' in source_node['attributes']:
                target_node['changed'] = source_node['attributes']['changed']
            # if 'field_paragraph' in source_node['attributes'] and source_node['attributes']['field_paragraph']:
            #     target_node['paragraph'] = source_node['attributes']['field_paragraph']
            # if 'field_text' in source_node['attributes'] and source_node['attributes']['field_text'] and 'value' in source_node['attributes']['field_text'] and source_node['attributes']['field_text']['value']:
            #     target_node['text'] = source_node['attributes']['field_text']['value']
            # if 'field_metatag' in source_node['attributes'] and source_node['attributes']['field_metatag'] and isinstance(source_node['attributes']['field_metatag'], dict) and 'value' in source_node['attributes']['field_metatag']:
            #     target_node['metatag'] = source_node['attributes']['field_metatag']['value']['description']
            
            # Extract all attributes with string values longer than 80 characters
            attributes = source_node.get('attributes', {})
            for key, value in attributes.items():
                extracted_value = self.extract_long_string_values(value)
                if extracted_value:
                    if not target_node.get('attributes', {}):
                        target_node['attributes'] = {}
                    key_str = key if not key.startswith('field_') else key[6:]
                    agglo_value = '\r\n'.join(extracted_value)
                    target_node['attributes'][key_str] = txt.fix_special_chars(agglo_value)

            if any(included_relationships):
                target_node['related_url'] = {}
                for rel in included_relationships:
                    if rel in source_node['relationships'] and 'related' in source_node['relationships'][rel]['links']:
                        target_node['related_url'][rel if not rel.startswith('field_') else rel[6:]] = source_node['relationships'][rel]['links']['related']['href']
            
            if any(included_relationships_ids):
                target_node['related_ids'] = {}
                for rel in included_relationships_ids:
                    if rel in source_node['relationships'] and 'data' in source_node['relationships'][rel] and source_node['relationships'][rel] and source_node['relationships'][rel]['data']:
                        if isinstance(source_node['relationships'][rel]['data'], list):
                            target_node['related_ids'][rel if not rel.startswith('field_') else rel[6:]] = [x['id'] for x in source_node['relationships'][rel]['data']]
                        elif 'id' in source_node['relationships'][rel]['data']:
                            target_node['related_ids'][rel if not rel.startswith('field_') else rel[6:]] = source_node['relationships'][rel]['data']['id']

            target_node = txt.fix_special_chars(target_node)
            items.append(target_node)
        return items
    
    def set_attribut_value_from_source(self, target_node, source_node, attribut_name:str):
        value = self.get_value_from_source(source_node['attributes'], attribut_name)
        if value:
            target_node[attribut_name] = value

    def get_value_from_source(self, source_node, attribut_name:str):
        if not attribut_name in source_node or not source_node[attribut_name]:
            return None
        if isinstance(source_node[attribut_name], dict) and 'value' in source_node[attribut_name]:
            if source_node[attribut_name]['value'] and isinstance(source_node[attribut_name]['value'], list):
                return '\r\n'.join(source_node[attribut_name]['value'])
            else:
                return source_node[attribut_name]['value']
        elif isinstance(source_node[attribut_name], str):
            return source_node[attribut_name]
        return None

    def extract_long_string_values(self, item: any, min_length:int=80, auto_include_exceptions:list[str]=['title', 'name', 'description']) -> list[str]:
        """
        Recursively extract string values from an item where the values are strings longer than the specified length.

        :param item: The item to extract values from
        :param min_length: The minimum length of the string to be extracted
        :return: A list of extracted strings longer than min_length
        """
        extracted_values = []
        if isinstance(item, str):
            if len(item) > min_length and not item.startswith('https://') and not item.startswith('http://'):
                extracted_values.append(txt.fix_special_chars(item))
        elif isinstance(item, dict):
            for key, value in item.items():
                if key not in ['relationships', 'links'] + auto_include_exceptions:
                    extracted_values.extend(self.extract_long_string_values(value, min_length))
                elif key in auto_include_exceptions:
                    auto_inc_value = self.get_value_from_source(item, key)
                    if auto_inc_value:
                        if isinstance(auto_inc_value, str):
                            extracted_values.append(auto_inc_value)
                        elif isinstance(auto_inc_value, list):
                            extracted_values.extend(auto_inc_value)
        elif isinstance(item, list):
            for element in item:
                extracted_values.extend(self.extract_long_string_values(element, min_length))
        return extracted_values

    def get_drupal_data_recursively(self, url: str, fetch_all_pages=True):
        items_full = self._perform_request(url)
        items_data = items_full['data']
        items = []
        items.extend(items_data)

        if fetch_all_pages and 'next' in items_full['links']:
            next_url = items_full['links']['next']['href']
            txt.print(f"Loading next page to URL: {next_url}")
            items += self.get_drupal_data_recursively(next_url, fetch_all_pages)
        return items
    
    def parallel_get_items_related_infos(self, items):
        def fetch_item_details(item):
            if 'related_url' in item:
                item['related_infos'] = {}
                for rel in item['related_url']:
                    related_infos = self._perform_request(item['related_url'][rel])
                    item['related_infos'][rel] = DrupalJsonApiClient.extract_all_field_text_values(related_infos)
            return item

        txt.print(f"Fetching related infos on {len(items)} items, for a global requests count of  {len(items)* len(items[0]['related_url'].keys())}...")
        
        # Use ThreadPoolExecutor to parallelize the fetch_items_details method
        with ThreadPoolExecutor(max_workers=50) as executor:
            # Submit all jobs that have 'related_url' for parallel execution
            futures = {executor.submit(fetch_item_details, job): job for job in items if 'related_url' in job}

            # Process the results as they complete
            for future in as_completed(futures):
                item = futures[future]
                try:
                    # Update the original job with the related infos
                    result = future.result()
                    items[items.index(item)] = result
                except Exception as ex:
                    print(f">>> Item {item} generated an exception: {ex}")

        return items

    @staticmethod
    def extract_all_field_text_values(json_data):
        """
        Extract all 'value' as str from all found 'field_text' keys in the given JSON structure.
        
        :param json_data: The JSON data to search within
        :return: A list of all extracted 'value' fields
        """
        field_text_values = []

        def extract_field_text_values(data):
            # Check if 'field_text' with 'value' exists in current dict
            if isinstance(data, dict):
                if 'field_text' in data and data['field_text'] and 'value' in data['field_text'] and data['field_text']['value']:
                    datum = data['field_text']['value']                    
                    datum = txt.fix_special_chars(datum)
                    if isinstance(datum, list):
                        for single_datum in datum:
                            field_text_values.append(single_datum)
                    elif isinstance(datum, str):
                        field_text_values.append(datum)
                    else:
                        raise ValueError(f"Unexpected data type in field_text 'value' field. Only str and list are supported, but got: {type(datum)}")
                # Recursively check nested dictionaries and lists
                for key, value in data.items():
                    extract_field_text_values(value)
            elif isinstance(data, list):
                for item in data:
                    extract_field_text_values(item)

        extract_field_text_values(json_data)
        field_text_values = DrupalJsonApiClient.remove_redundant_strings_based_on_similarity_threshold(field_text_values, similarity_threshold=0.3)
        return field_text_values
    
    #todo: to move to common_tools, BM25 section
    @staticmethod
    def remove_redundant_strings_based_on_similarity_threshold(phrases: list[str], similarity_threshold: float = 0.5) -> list[str]:
        """
        Removes similar phrases from a list, retaining the most informative one based on BM25 similarity.

        :param phrases: List of strings to analyze for redundancy.
        :param similarity_threshold: A threshold (0 to 1) above which phrases are considered redundant.
        :return: A list of unique phrases with redundancy removed, keeping the most informative ones.
        """
        # Tokenize the phrases
        tokenized_phrases = [phrase.split() for phrase in phrases]
        
        # Initialize BM25 model
        bm25 = BM25Okapi(tokenized_phrases)
        
        # Keep track of which phrases to retain
        to_keep = np.ones(len(phrases), dtype=bool)
        
        # Iterate over each phrase to compare it with others using BM25
        for i, phrase in enumerate(phrases):
            if to_keep[i]:
                # Query BM25 with the current phrase
                scores = bm25.get_scores(phrase.split())
                
                # Identify similar phrases based on the similarity threshold
                similar_indices = [j for j, score in enumerate(scores) if score / max(scores) >= similarity_threshold and j != i]
                
                # Include the current phrase's index in the list of similar phrases
                similar_indices.append(i)
                
                # Find the most informative phrase (longest one)
                most_informative_index = max(similar_indices, key=lambda idx: len(phrases[idx].split()))
                
                # Mark all other similar phrases for deletion except the most informative
                for idx in similar_indices:
                    if idx != most_informative_index:
                        to_keep[idx] = False
        
        # Return the filtered list containing the most informative phrases
        return [phrase for i, phrase in enumerate(phrases) if to_keep[i]]


    @staticmethod
    def remove_redundant_strings_wo_score(phrases: list[str]) -> list[str]:
        """
        Removes similar phrases from a list, retaining the most informative one based on BM25 similarity.

        :param phrases: List of strings to analyze for redundancy.
        :param similarity_threshold: A threshold (0 to 1) above which phrases are considered redundant.
        :return: A list of unique phrases with redundancy removed, keeping the most informative ones.
        """
        # Convert the input list to LangChain Document objects
        documents = [Document(page_content=phrase) for phrase in phrases]
        
        # Initialize the BM25Retriever with the documents
        bm25_retriever = BM25Retriever.from_texts([doc.page_content for doc in documents])
        
        # Keep track of which phrases to retain
        to_keep = np.ones(len(phrases), dtype=bool)
        
        # Iterate over each phrase to compare it with others using BM25
        for i, phrase in enumerate(phrases):
            if to_keep[i]:
                # Get the scores for the phrase against the entire list
                results = bm25_retriever.get_relevant_documents(phrase)
                
                # Collect indices of similar phrases
                similar_indices = []
                
                for result in results:
                    # Get the index of the matching document
                    j = phrases.index(result.page_content)
                    
                    # Skip if it's the same document or already marked for removal
                    if i != j and to_keep[j]:
                        similar_indices.append(j)
                        to_keep[j] = False
                
                # Include the current phrase's index in the list of similar phrases
                similar_indices.append(i)
                
                # Find the most informative phrase (longest one)
                most_informative_index = max(similar_indices, key=lambda idx: len(phrases[idx].split()))
                
                # Mark all other similar phrases for deletion except the most informative
                for idx in similar_indices:
                    if idx != most_informative_index:
                        to_keep[idx] = False
        
        # Return the filtered list containing the most informative phrases
        return [phrase for i, phrase in enumerate(phrases) if to_keep[i]]

