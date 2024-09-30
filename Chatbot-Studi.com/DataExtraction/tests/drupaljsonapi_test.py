# test_drupal_client.py

import pytest
from unittest.mock import patch
from drupal_json_api import DrupalJsonApiClient

class TestDrupalJsonApiClient:
    def setup_method(self):
        # Initialize the client with a base_url suitable for testing
        self.client = DrupalJsonApiClient(base_url="https://jsonplaceholder.typicode.com/")

    def test_perform_request(self):
        """
        Test the _perform_request method with an actual HTTP request to a safe URL.
        """
        # Using jsonplaceholder.typicode.com as a safe testing endpoint
        response = self.client._perform_request('posts/1')
        assert response is not None
        assert 'id' in response
        assert response['id'] == 1
        assert 'title' in response

    @patch.object(DrupalJsonApiClient, '_perform_request')
    def test_get_drupal_data_recursively(self, mock_perform_request):
        """
        Test the get_drupal_data_recursively method by mocking _perform_request to avoid actual HTTP requests.
        """
        # Prepare fake responses for pagination
        fake_response_page1 = {
            'data': [
                {
                    'id': '1',
                    'type': 'node--jobs',
                    'attributes': {
                        'title': 'Job 1',
                        'field_text': {'value': 'Job 1 description'}
                    },
                    'relationships': {},
                },
                {
                    'id': '2',
                    'type': 'node--jobs',
                    'attributes': {
                        'title': 'Job 2',
                        'field_text': {'value': 'Job 2 description'}
                    },
                    'relationships': {}
                }
            ],
            'links': {
                'next': {'href': 'http://example.com/page2'}
            }
        }

        fake_response_page2 = {
            'data': [
                {
                    'id': '3',
                    'type': 'node--jobs',
                    'attributes': {
                        'title': 'Job 3',
                        'field_text': {'value': 'Job 3 description'}
                    },
                    'relationships': {}
                }
            ],
            'links': {}
        }

        # Define side effects for the mocked _perform_request method
        def side_effect(url, params=None):
            if 'node/jobs' in url:
                return fake_response_page1
            elif 'http://example.com/page2' in url:
                return fake_response_page2
            else:
                return {}

        mock_perform_request.side_effect = side_effect

        # Call the method under test
        items = self.client.get_drupal_data_recursively(
            'node/jobs',
            self.client.get_generic_data_from_node_item,
            included_relationships=[], 
            included_relationships_ids=[]
        )

        # Assertions to verify the expected behavior
        assert len(items) == 3
        titles = [item['title'] for item in items]
        assert 'Job 1' in titles
        assert 'Job 2' in titles
        assert 'Job 3' in titles

    def test_get_generic_data_from_node_item_with_relationships(self):
        """
        Test the get_generic_data_from_node_item method with generalized relationship processing and updated parameters.
        """
        # Prepare fake list of items_data
        items_data = [
            {
                'id': '1',
                'type': 'node--article',
                'attributes': {
                    'title': 'Article 1',
                    'body': {'value': 'Main article content...' * 5}  # Over 80 chars
                },
                'relationships': {
                    'field_paragraph': {
                        'data': [
                            {'type': 'paragraph--text', 'id': 'p1'},
                            {'type': 'paragraph--text', 'id': 'p2'}
                        ]
                    }
                },
                'links': {}
            }
        ]

        # Included data representing paragraphs linked in the relationships
        included_data = [
            {
                'id': 'p1',
                'type': 'paragraph--text',
                'attributes': {
                    'field_text': {'value': 'Paragraph 1 text...' * 4}  # Over 80 chars
                }
            },
            {
                'id': 'p2',
                'type': 'paragraph--text',
                'attributes': {
                    'field_text': {'value': 'Short text'}  # Less than 80 chars
                }
            }
        ]

        # Relationships to include as 'included_rel_ids'
        included_rel_ids = ['field_paragraph']

        # Call the method under test with the updated parameters
        items = self.client.get_generic_data_from_node_item(
            items_data, included_rel_ids=included_rel_ids
        )

        # Assertions
        assert len(items) == 1
        item = items[0]
        assert item['id'] == '1'
        assert item['title'] == 'Article 1'
        #assert 'body' in item
        assert 'related_ids' in item
        assert 'paragraph' in item['related_ids']
        related_ids = item['related_ids']['paragraph']
        assert len(related_ids) == 2
        assert 'p1' in related_ids
        assert 'p2' in related_ids

        # Validate that related_infos and length checks for paragraphs are correct
        assert 'related_infos' not in item  # As the new method does not generate 'related_infos'

    def test_extract_field_text_values(self):
        """
        Test the extract_field_text_values static method.
        """
        # Prepare fake items
        items = [
            {
                'attributes': {
                    'field_text': {'value': 'Text 1'}
                }
            },
            {
                'attributes': {
                    'field_text': {'value': 'Text 2'}
                }
            },
            {
                'attributes': {
                    'field_text': {'value': ['Text 3', 'Text 4']}
                }
            }
        ]

        # Call the method under test
        texts = self.client.extract_field_text_values(items)

        # Assertions to verify the expected behavior
        assert texts == ['Text 1', 'Text 2', 'Text 3', 'Text 4']

    def test_remove_redundant_str(self):
        """
        Test the remove_redundant_str static method.
        """
        # Prepare fake list of strings
        strings = [
            "The quick brown fox jumps over the lazy dog.",
            "The quick brown fox jumps over a lazy dog.",
            "A quick brown fox leaps over the lazy dog with grace and agility.",
            "The quick brown fox jumps.",
            "A fast brown fox jumped over the lazy dog."
        ]

        # Call the method under test
        unique_strings = DrupalJsonApiClient.remove_redundant_strings_based_on_similarity_threshold(phrases=strings, similarity_threshold=0.30)

        # Assertions to verify the expected behavior
        assert len(unique_strings) == 2
        assert "A quick brown fox leaps over the lazy dog with grace and agility." in unique_strings
        assert "The quick brown fox jumps." in unique_strings

    def test_remove_redundant_str_no_removal(self):
        """
        Test the remove_redundant_str static method when sentences are unique and should not be removed.
        """
        # Prepare fake list of strings with unique information
        strings = [
            "The quick brown fox jumps over the lazy dog.",
            "The quick brown fox quickly finds shelter.",
            "A red fox hunts in the moonlight.",
            "The fox is known for its cunning nature.",
            "Foxes adapt to various environments worldwide."
        ]

        # Call the method under test with a low similarity threshold to ensure no removal
        unique_strings = DrupalJsonApiClient.remove_redundant_strings_based_on_similarity_threshold(phrases=strings, similarity_threshold=0.30)

        # Assertions to verify that all strings are retained as they are unique
        assert len(unique_strings) == len(strings)
        assert set(unique_strings) == set(strings)




