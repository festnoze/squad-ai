from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import requests

from common_tools.helpers import txt

class DrupalJsonApiClient:
    BASE_URL = "https://www.studi.com/jsonapi/"

    def _perform_request(self, endpoint):
        """
        Makes a GET request to the specified JSON:API endpoint.
        
        :param endpoint: The JSON:API item (e.g. 'node/article' for: /jsonapi/node/article)
        :return: The JSON response or an error message if the request fails
        """
        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
            return response.json()  # Return the JSON response if the request is successful
        except requests.RequestException as e:
            print(f"Error fetching data from {url}: {e}")
            return None

    # def get_articles_filter_status_1(self):
    #     return self._perform_request('article?filter[status]=1')

    # def get_article_include_uid(self):
    #     return self._perform_request('article?include=uid')

    # def get_article_page_limit__5_page_offset__0(self):
    #     return self._perform_request('article?page[limit]=5&page[offset]=0')

    # def get_article_sort_created(self):
    #     return self._perform_request('article?sort=created')

    def get_jobs(self):
        jobs = self.get_drupal_data_recursivly('node/jobs', self.get_generic_data_from_node_item, ['field_paragraph'], ['field_domain'])
        jobs = self.parallel_get_items_related_infos(jobs)
        return jobs
  
    def get_fundings(self):
        return self.get_drupal_data_recursivly('node/funding?include=field_paragraph', self.get_generic_data_from_node_item)      
      
    def get_fundings(self):
        return self.get_drupal_data_recursivly('taxonomy_term/domain?include=field_school', self.get_generic_data_from_node_item)  
    
    def get_trainings(self):
        trainings = self.get_drupal_data_recursivly('node/training', self.get_generic_data_from_node_item, ['field_certification', 'field_diploma', 'field_funding', 'field_goal', 'field_job'])
        trainings = self.parallel_get_items_related_infos(trainings)
        return trainings
    
    # def get_trainings_details(self):
    #     return self.get_drupal_data_recursivly('training?include=field_certification&include=field_diploma&include=field_funding&include=field_goal&include=field_job', self.get_trainings_from_data)
    

    def get_generic_data_from_node_item(self, items_data, included_rel=[], included_rel_ids=[]):
        items = []
        for i, item in enumerate(items_data):
            new_item ={
                'id': item['id'],
                'title': item['attributes']['title'],
                'type': item['type']
            }
            if 'related' in item['links']:
                new_item['related_url'] = item['links']['related']['href']
            if 'field_paragraph' in item['attributes']:
                new_item['field_paragraph'] = item['attributes']['field_paragraph']
            if 'field_text' in item['attributes']:
                new_item['field_text'] = item['attributes']['field_text']['value']
            if 'field_metatag' in item['attributes'] and item['attributes']['field_metatag'] and 'value' in item['attributes']['field_metatag']:
                new_item['field_metatag'] = item['attributes']['field_metatag']['value']['description']
            if 'changed' in item['attributes'] and item['attributes']['changed']:
                new_item['changed'] = item['attributes']['changed']
            if any(included_rel):
                new_item['related_url'] = {}
                for rel in included_rel:
                    if rel in item['relationships'] and 'related' in item['relationships'][rel]['links']:
                        new_item['related_url'][rel] = item['relationships'][rel]['links']['related']['href']
            if any(included_rel_ids):
                new_item['related_ids'] = {}
                for rel in included_rel_ids:
                    if rel in item['relationships'] and 'data' in item['relationships'][rel] and 'id' in item['relationships'][rel]['data']:
                        new_item['related_ids'][rel] = item['relationships'][rel]['data']['id']
            # if 'field_paragraph' in  item['relationships'] and 'related' in item['relationships']['field_paragraph']['links']:
            #     new_item['related_url'] =  item['relationships']['field_paragraph']['links']['related']['href']
            
            new_item = txt.fix_special_chars(new_item)
            items.append(new_item)
        return items
    
    # def get_trainings_from_data(self, trainings_data):
    #     trainings = []
    #     for i, training in enumerate(trainings_data):
    #         new_training ={
    #             'id': training['id'],
    #             'title': training['attributes']['title'],
    #             'type': training['type']
    #         }
    #         if 'field_paragraph' in training['attributes']:
    #             new_training['field_paragraph'] = training['attributes']['field_paragraph']
    #         if 'field_text' in training['attributes']:
    #             new_training['field_text'] = training['attributes']['field_text']['value']
    #         if 'field_metatag' in training['attributes'] and training['attributes']['field_metatag'] and 'value' in training['attributes']['field_metatag']:
    #             new_training['field_metatag'] = training['attributes']['field_metatag']['value']['description']
            
    #         new_training = txt.fix_special_chars(new_training)
    #         trainings.append(training)
    #     return trainings
    
    def get_drupal_data_recursivly(self, url: str, delegate, included_relationships=[], included_relationships_ids=[], fetch_all_pages=False):
        items_full = self._perform_request(url)
        items_data = items_full['data']
        items = []
        items.extend(delegate(items_data, included_relationships, included_relationships_ids))

        if fetch_all_pages and 'next' in items_full['links']:
            next_url = items_full['links']['next']['href']
            txt.print(f"Loading next page to URL: {next_url}")
            jobs += self.get_drupal_data_recursivly(next_url, delegate, included_relationships, included_relationships_ids, fetch_all_pages)
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
                    field_text_values.append(datum)
                # Recursively check nested dictionaries and lists
                for key, value in data.items():
                    extract_values(value)
            elif isinstance(data, list):
                for item in data:
                    extract_values(item)

        extract_values(json_data)
        return field_text_values
