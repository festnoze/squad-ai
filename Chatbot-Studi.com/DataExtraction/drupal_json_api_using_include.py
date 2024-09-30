import time
import requests
from typing import List, Dict, Any

from common_tools.helpers import txt

class DrupalJsonApiClient:
    def __init__(self, base_url="https://www.studi.com/jsonapi/"):
        self.BASE_URL = base_url

    # def get_articles_filter_status_1(self):
    #     return self._perform_request('article?filter[status]=1')

    # def get_article_include_uid(self):
    #     return self._perform_request('article?include=uid')

    # def get_article_page_limit__5_page_offset__0(self):
    #     return self._perform_request('article?page[limit]=5&page[offset]=0')

    # def get_article_sort_created(self):
    #     return self._perform_request('article?sort=created')

    def get_jobs(self):
        jobs = self.get_drupal_data_recursively('node/jobs', self.get_attributes_values_from_node_item, ['field_paragraph'])
        return jobs
  
    def get_fundings(self):
        return self.get_drupal_data_recursively('node/funding', self.get_attributes_values_from_node_item, ['field_paragraph'])      
      
    def get_domains(self):
        return self.get_drupal_data_recursively('taxonomy_term/domain', self.get_attributes_values_from_node_item, ['field_school'])  
    
    def get_trainings(self):
        trainings = self.get_drupal_data_recursively('node/training', self.get_attributes_values_from_node_item, ['field_content_bloc'])#, ['field_certification', 'field_diploma', 'field_funding', 'field_goal', 'field_job'])
        return trainings

    def _perform_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Makes a GET request to the specified JSON:API endpoint with given query parameters.
        
        :param endpoint: The JSON:API item (e.g., 'node/article' for: /jsonapi/node/article)
        :param params: A dictionary of query parameters to include in the request
        :return: The JSON response
        :raises: Exception if the request fails
        """
        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = f"{self.BASE_URL}{endpoint}"

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching data from {url} with params {params}: {e}")

    def get_drupal_data_recursively(
        self,
        url: str,
        delegate,
        included_rels: List[str] = [],
        page_limit: int = 32,
        max_retries: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Fetch data recursively from Drupal JSON API, including specified relationships.
        Handles pagination and retries in case of failures.

        :param url: The endpoint to fetch data from
        :param delegate: The function to process the items
        :param included_rels: List of relationships to include
        :param page_limit: Number of items per page
        :param max_retries: Maximum number of retries in case of failure
        :return: List of items
        """
        params = {}
        if included_rels:
            params['include'] = ','.join(included_rels)
        params['page[limit]'] = page_limit

        items = []
        next_url = None

        while True:
            retries = 0
            success = False
            current_url = next_url if next_url else url

            while retries < max_retries and not success:
                try:
                    response = self._perform_request(current_url, params if not next_url else None)
                    if response:
                        success = True
                except Exception as e:
                    retries += 1
                    time.sleep(retries * 3)
                    if page_limit >= 2:
                        page_limit = int(page_limit / 2)
                        txt.print(f"Reducing page_limit to {page_limit} and retrying.")
                        params['page[limit]'] = page_limit

            if success:
                items_data = response['data']
                included_data = response.get('included', [])
                combined_data = {
                    'items_data': items_data,
                    'included_data': included_data
                }

                return [combined_data]
                items.extend(delegate(items_data, included_rels, included_data))

                # Check for next page link
                links = response.get('links', {})
                next_link = links.get('next', {}).get('href')
                if next_link:
                    next_url = next_link
                    txt.print(f"Fetching next page: {next_url}")
                else:
                    break
            else:
                print("Error: Reached an unexpected state without success.")
                break

        return items

    def get_attributes_values_from_node_item(
        self,
        items_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process the data items and include related data from the 'included' array.

        :param items_data: The main data items
        :param included_rel: List of relationships that were included
        :param included_data: The included related entities
        :return: List of processed items
        """
        items = []
        for item in items_data:
            new_item = {
                'id': item.get('id', ''),
                'title': item.get('attributes', {}).get('title', ''),
                'type': item.get('type', ''),
            }

            # Extract attributes with string values longer than 80 characters
            attributes = item.get('attributes', {})
            for key, value in attributes.items():
                extracted_value = self.extract_long_string_values(value)
                if extracted_value:
                    if not new_item.get('attributes', {}):
                        new_item['attributes'] = {}
                    key_str = key if not key.startswith('field_') else key[6:]
                    new_item['attributes'][key_str] = txt.fix_special_chars(extracted_value[0])
        return items
                    
    # def get_relationships_values_from_(self, included_rel: List[str], included_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            
    #     items_related_infos = []
    #     included_map = None
    #     if not any(included_data):
    #         return None
        
    #     included_map = {
    #         (item['type'], item['id']): item for item in included_data
    #     }
    #     # Process included relationships
    #     if included_rel:
    #         item_related_infos = {}
    #         for rel in included_rel:
    #             rel_data = item.get('relationships', {})
    #             if not rel_data:
    #                 continue
    #             for key, value in rel_data.items():
    #                 rel_data = value.get('data', [])
    #                 if not rel_data:
    #                     continue
    #                 related_items = []
    #                 if isinstance(rel_data, dict):
    #                     # Single relationship
    #                     key1 = (rel_data['type'], rel_data['id'])
    #                     if included_map and key1 in included_map:
    #                         related_item = included_map.get(key1)
    #                         if related_item:
    #                             extracted_attributes = self.extract_long_string_values(related_item)
    #                     else:
    #                         extracted_attributes = self.extract_long_string_values(rel_data)
    #                     if extracted_attributes:
    #                         related_items.extend(extracted_attributes)
    #                 elif isinstance(rel_data, list):
    #                     # Multiple relationships
    #                     for rel_item in rel_data:
    #                         key1 = (rel_item['type'], rel_item['id'])
    #                         if included_map and key1 in included_map:
    #                             related_item = included_map.get(key1)
    #                             if related_item:
    #                                 extracted_attributes = self.extract_long_string_values(related_item)                                
    #                         else:
    #                             extracted_attributes = self.extract_long_string_values(rel_item)
    #                             if extracted_attributes:
    #                                 related_items.extend(extracted_attributes)
    #                 if related_items:
    #                     new_item['related_infos'][key] = related_items

    #     items.append(new_item)

    #     return items

    def extract_long_string_values(self, item: Any, min_length=80) -> List[str]:
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
                if key not in ['relationships', 'links']:
                    extracted_values.extend(self.extract_long_string_values(value, min_length))
        elif isinstance(item, list):
            for element in item:
                extracted_values.extend(self.extract_long_string_values(element, min_length))

        return extracted_values

    @staticmethod
    def extract_field_text_values(items: List[Dict[str, Any]]) -> List[str]:
        """
        Extract 'field_text' values from items.

        :param items: List of items
        :return: List of 'field_text' values
        """
        texts = []
        for item in items:
            field_text = item['attributes'].get('field_text', {})
            if field_text and 'value' in field_text:
                texts.append(field_text['value'])
        return texts
