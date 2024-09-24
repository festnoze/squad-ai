from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from common_tools.helpers.txt_helper import txt

class DrupalJsonApiClient:
    BASE_URL = "https://www.studi.com"

    def _perform_request(self, endpoint):
        """
        Makes a GET request to the specified JSON:API endpoint.
        
        :param endpoint: The JSON:API endpoint (e.g., /jsonapi/node/article)
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

    # Generated methods for each endpoint
    def get_articles(self):
        return self._perform_request('/jsonapi/node/article')

    def get_articles_filter_status_1(self):
        return self._perform_request('/jsonapi/node/article?filter[status]=1')

    def get_article_include_uid(self):
        return self._perform_request('/jsonapi/node/article?include=uid')

    def get_article_page_limit__5_page_offset__0(self):
        return self._perform_request('/jsonapi/node/article?page[limit]=5&page[offset]=0')

    def get_article_sort_created(self):
        return self._perform_request('/jsonapi/node/article?sort=created')

    def get_jobs(self):
        return self.get_jobs_from_url('/jsonapi/node/jobs')

    def get_jobs_from_url(self, url: str):
        jobs_full = self._perform_request(url)
        jobs_data = jobs_full['data']
        jobs = []
        for i, job in enumerate(jobs_data):
            new_job ={
                'id': job['id'],
                'title': job['attributes']['title'],
                'type': job['type']
            }
            if 'related' in job['links']:
                new_job['related_url'] = job['links']['related']['href']
            if 'field_paragraph' in job['attributes']:
                new_job['field_paragraph'] = job['attributes']['field_paragraph']
            if 'field_text' in job['attributes']:
                new_job['field_text'] = job['attributes']['field_text']['value']
            if 'field_metatag' in job['attributes'] and job['attributes']['field_metatag'] and 'value' in job['attributes']['field_metatag']:
                new_job['field_metatag'] = job['attributes']['field_metatag']['value']['description']
            if job['relationships']['field_paragraph']['links']['related']['href']:
                new_job['related_url'] =  job['relationships']['field_paragraph']['links']['related']['href']
            
            new_job = txt.fix_special_chars(new_job)
            jobs.append(new_job)

            txt.print(f"Job {i+1}/{len(jobs_data)}: {new_job['title']}")
        if 'next' in jobs_full['links']:
            next_url = jobs_full['links']['next']['href']
            txt.print(f"Next jobs page to URL: {next_url}")
            jobs += self.get_jobs_from_url(next_url)
        return jobs
    
    def get_jobs_details(self, jobs):
        for i, job in enumerate(jobs):
            if 'related_url' in job:
                job['related'] = self._perform_request(job['related_url'])
                job['related_infos'] = DrupalJsonApiClient.extract_field_text_values(job['related'])

    def get_jobs_details_parallel(self, jobs):
        def fetch_job_details(job):
            if 'related_url' in job:
                related = self._perform_request(job['related_url'])
                job['related_infos'] = DrupalJsonApiClient.extract_field_text_values(related)
            return job

        # Use ThreadPoolExecutor to parallelize the fetch_job_details function
        with ThreadPoolExecutor(max_workers=50) as executor:
            # Submit all jobs that have 'related_url' for parallel execution
            futures = {executor.submit(fetch_job_details, job): job for job in jobs if 'related_url' in job}

            # Process the results as they complete
            for future in as_completed(futures):
                job = futures[future]
                try:
                    # Update the original job with the fetched details
                    result = future.result()
                    jobs[jobs.index(job)] = result
                except Exception as exc:
                    print(f"Job {job} generated an exception: {exc}")

        return jobs

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

    def get_jobs_with_details(self):
        return self._perform_request('/jsonapi/node/jobs?include=field_paragraph')

    def get_trainings(self):
        return self._perform_request('/jsonapi/node/training')
