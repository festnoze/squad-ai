from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from langchain.retrievers import BM25Retriever
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

    def get_jobs(self):
        jobs = self.get_drupal_data_recursively('node/jobs', self.get_generic_data_from_node_item, ['field_paragraph'], ['field_domain'])
        jobs = self.parallel_get_items_related_infos(jobs)
        return jobs
    
    def get_fundings(self):
        fundings = self.get_drupal_data_recursively('node/funding', self.get_generic_data_from_node_item, ['field_paragraph'])      
        fundings = self.parallel_get_items_related_infos(fundings)
        return fundings
    
    def get_trainings(self):
        trainings = self.get_drupal_data_recursively('node/training', self.get_generic_data_from_node_item, ['field_paragraph'], ['field_content_bloc','field_certification', 'field_diploma', 'field_domain', 'field_job', 'field_funding', 'field_goal', 'field_job'])
        return trainings

    def get_diplomas(self):
        diplomas = self.get_drupal_data_recursively('node/diploma', self.get_generic_data_from_node_item, ['field_paragraph'], ['field_content_bloc','field_certification', 'field_diploma', 'field_domain', 'field_job', 'field_funding', 'field_goal', 'field_job'])
        diplomas = self.parallel_get_items_related_infos(diplomas)
        return diplomas
    
    def get_certifications(self):
        return self.get_drupal_data_recursively('taxonomy_term/certification', self.get_generic_data_from_node_item, ['field_paragraph'])
    
    def get_domains(self):
        return self.get_drupal_data_recursively('taxonomy_term/domain', self.get_generic_data_from_node_item, ['field_paragraph', 'field_school'], ['field_jobs'])  
    

    def _perform_request(self, endpoint, allowed_retries=3):
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
            if allowed_retries > 0: # Retry 'allowed_retries' times upon request failure
                return self._perform_request(endpoint, allowed_retries=allowed_retries-1)
            raise e

    # def get_articles_filter_status_1(self):
    #     return self._perform_request('article?filter[status]=1')

    # def get_article_include_uid(self):
    #     return self._perform_request('article?include=uid')

    # def get_article_page_limit__5_page_offset__0(self):
    #     return self._perform_request('article?page[limit]=5&page[offset]=0')

    # def get_article_sort_created(self):
    #     return self._perform_request('article?sort=created')
    
    def get_generic_data_from_node_item(self, items_data, included_rel=[], included_rel_ids=[]):
        items = []
        for i, item in enumerate(items_data):
            new_item ={
                'id': item['id'],
                'type': item['type']
            }
            if not 'attributes' in item:
                continue
            if 'title' in item['attributes'] and item['attributes']['title']:
                if isinstance(item['attributes']['title'], dict) and 'value' in item['attributes']['title']:
                    new_item['title'] = item['attributes']['title']['value']
                else:
                    new_item['title'] = item['attributes']['title']
            elif 'name' in item['attributes'] and item['attributes']['name']:
                if isinstance(item['attributes']['name'], dict) and 'value' in item['attributes']['name']:
                    new_item['title'] = item['attributes']['name']['value']
                else:
                    new_item['title'] = item['attributes']['name']
            if 'description' in item['attributes'] and item['attributes']['description']:
                if isinstance(item['attributes']['description'], dict) and 'value' in item['attributes']['description']:
                    new_item['description'] = item['attributes']['description']['value']
                else:
                    new_item['description'] = item['attributes']['description']
            if 'links' in item and 'related' in item['links']:
                new_item['related_url'] = item['links']['related']['href']
            if 'field_paragraph' in item['attributes']:
                new_item['field_paragraph'] = item['attributes']['field_paragraph']
            if 'field_text' in item['attributes']:
                new_item['field_text'] = item['attributes']['field_text']['value']
            if 'field_metatag' in item['attributes'] and item['attributes']['field_metatag'] and isinstance(item['attributes']['field_metatag'], dict) and 'value' in item['attributes']['field_metatag']:
                new_item['field_metatag'] = item['attributes']['field_metatag']['value']['description']
            if 'changed' in item['attributes'] and item['attributes']['changed']:
                new_item['changed'] = item['attributes']['changed']
            if any(included_rel):
                new_item['related_url'] = {}
                for rel in included_rel:
                    if rel in item['relationships'] and 'related' in item['relationships'][rel]['links']:
                        new_item['related_url'][rel if not rel.startswith('field_') else rel[6:]] = item['relationships'][rel]['links']['related']['href']
            if any(included_rel_ids):
                new_item['related_ids'] = {}
                for rel in included_rel_ids:
                    if rel in item['relationships'] and 'data' in item['relationships'][rel] and item['relationships'][rel] and item['relationships'][rel]['data']:
                        if isinstance(item['relationships'][rel]['data'], list):
                            new_item['related_ids'][rel if not rel.startswith('field_') else rel[6:]] = [x['id'] for x in item['relationships'][rel]['data']]
                        elif 'id' in item['relationships'][rel]['data']:
                            new_item['related_ids'][rel if not rel.startswith('field_') else rel[6:]] = item['relationships'][rel]['data']['id']

            new_item = txt.fix_special_chars(new_item)
            items.append(new_item)
        return items
    
    def get_drupal_data_recursively(self, url: str, delegate, included_relationships=[], included_relationships_ids=[], fetch_all_pages=True):
        items_full = self._perform_request(url)
        items_data = items_full['data']
        items = []
        items.extend(delegate(items_data, included_relationships, included_relationships_ids))

        if fetch_all_pages and 'next' in items_full['links']:
            next_url = items_full['links']['next']['href']
            txt.print(f"Loading next page to URL: {next_url}")
            items += self.get_drupal_data_recursively(next_url, delegate, included_relationships, included_relationships_ids, fetch_all_pages)
        return items
    
    def parallel_get_items_related_infos(self, items):
        def fetch_item_details(item):
            if 'related_url' in item:
                item['related_infos'] = {}
                for rel in item['related_url']:
                    related_infos = self._perform_request(item['related_url'][rel])
                    item['related_infos'][rel] = DrupalJsonApiClient.extract_field_text_values(related_infos)
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
    def extract_field_text_values(json_data):
        """
        Extract all 'value' fields from 'field_text' attributes in a given JSON structure.
        
        :param json_data: The JSON data to search within
        :return: A list of all extracted 'value' fields
        """
        field_text_values = []

        def extract_values(data):
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
                    extract_values(value)
            elif isinstance(data, list):
                for item in data:
                    extract_values(item)

        extract_values(json_data)
        field_text_values = DrupalJsonApiClient.remove_redundant_strings_based_on_similarity_threshold(field_text_values, similarity_threshold=0.3)
        return field_text_values
    
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
                        # Normalize the BM25 score
                        max_score = results[0].metadata['score']
                        normalized_score = result.metadata['score'] / max_score if max_score > 0 else 0
                        
                        if normalized_score >= similarity_threshold:
                            similar_indices.append(j)
                            to_keep[j] = False  # Mark as redundant initially
                
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

