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
                    'relationships': {}
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
            self.client.get_attributes_values_from_node_item,
            included_rels=[]
        )

        # Assertions to verify the expected behavior
        assert len(items) == 3
        titles = [item['title'] for item in items]
        assert 'Job 1' in titles
        assert 'Job 2' in titles
        assert 'Job 3' in titles

    def test_get_generic_data_from_node_item_with_relationships(self):
        """
        Test the get_generic_data_from_node_item method with generalized relationship processing.
        """
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
                }
            }
        ]

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

        included_rel = ['field_paragraph']

        # Call the method under test
        items = self.client.get_attributes_values_from_node_item(
            items_data, included_rel, included_data
        )

        # Assertions
        assert len(items) == 1
        item = items[0]
        assert item['id'] == '1'
        assert item['title'] == 'Article 1'
        assert 'body' in item
        assert 'related_infos' in item
        assert 'field_paragraph' in item['related_infos']
        related_infos = item['related_infos']['field_paragraph']
        assert len(related_infos) == 1  # Only one related item has long text
        related_item = related_infos[0]
        assert 'field_text' in related_item
        assert len(related_item['field_text']) > 80


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
                    'field_text': {'value': 'Text 3'}
                }
            }
        ]

        # Call the method under test
        texts = self.client.extract_field_text_values(items)

        # Assertions to verify the expected behavior
        assert texts == ['Text 1', 'Text 2', 'Text 3']
