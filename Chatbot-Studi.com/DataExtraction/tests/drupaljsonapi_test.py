# test_drupal_client.py

import pytest
from unittest.mock import patch
from drupal_json_api_client import DrupalJsonApiClient

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
        items = self.client.get_drupal_data_recursively('node/jobs')

        # Assertions to verify the expected behavior
        assert len(items) == 3
        ids = [item['id'] for item in items]
        assert '1' in ids
        assert '2' in ids
        assert '3' in ids
        titles = [item['attributes']['title'] for item in items]
        assert 'Job 1' in titles
        assert 'Job 2' in titles
        assert 'Job 3' in titles

    def test_extract_common_data_from_nodes_with_relationships(self):
        """
        Test the extract_common_data_from_nodes method with generalized relationship processing and updated parameters.
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
        items = self.client.extract_common_data_from_nodes(
            items_data,
            included_relationships= [], 
            included_relationships_ids=included_rel_ids
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

    def test_extract_all_field_text_values(self):
        """
        Test the extract_field_text_values static method.
        """
        # Prepare fake items
        items = [
            {
                'field_text': {'value': 'Text 1'}
            },
            {
                'fakenode': {
                    'innernode': {
                        'field_text': {'value': 'Text 2'}
                    }
                }
            },
            {
                'attributes': {
                    'field_text': {'value': ['Text 3', 'Text 4']}
                }
            }
        ]

        # Call the method under test
        texts = self.client.extract_all_field_text_values(items)

        # Assertions to verify the expected behavior
        assert texts == ['Text 1', 'Text 2', 'Text 3', 'Text 4']

    def test_remove_redundant_str_should_removed_duplicate_1(self):
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

    #todo: change phrases
    def test_remove_redundant_str_should_removed_duplicate_2(self):
        """
        Test the remove_redundant_str static method with complementary information.
        """
        # Prepare fake list of strings with unique or complementary information
        strings = [
            "Pilier de la stratégie publicitaire d’une marque, le planneur stratégique a pour mission principale de mettre ses yeux et ses oreilles au service d’une veille attentive des tendances, actuelles ou futures, de la société et des marchés. Il met au point et oriente les concepts des futures campagnes publicitaires ou de communication des entreprises. Pour ce faire, il sort, lit et échange beaucoup. Il s’appuie aussi sur de nombreuses études comportementales, analyses d’audience ou benchmarks concurrentiels.\r\n\r\nUne fois cette tendance analysée, il élabore un concept créatif en exploitant l'imaginaire ambiant (cinéma, design, littérature...). Puis il communique aux équipes créatives (concepteur rédacteur, directeur artistique, graphiste…) ces orientations publicitaires et marketing. Ce « brief » ou cahier des charges intègre aussi rétroplanning et éléments budgétaires.\r\n\r\nLe planneur stratégique est aussi le créateur de la plateforme de marque : un support qui précise les valeurs, l’environnement et le portrait-robot de la clientèle de l’entreprise cliente et qui vise à positionner la marque en cohérence avec la stratégie produit et les attentes du consommateur.\r\n\r\nLa profession de planneur stratégique est un segment professionnel de niche qui ne représente que quelques dizaines de personnes en France.",
            "Pour devenir planneur stratégique, il est recommandé d’avoir un niveau de formation bac + 3 à bac + 5 en sciences humaines (lettres, psychologie, sociologie, philosophie, droit...), et d’y adjoindre un cursus en communication, marketing ou publicité.\r\n\r\nVotre parcours de formation chez Studi",
            "Il trouve du travail difficilement (métier de niche) avec un bac + 5 minimum.\r\n\r\nIl a un caractère social, créatif, organisé, intellectuel et entreprenant.\r\n\r\nIl travaille dans le secteur privé, dans un bureau, en zone urbaine ou internationale, avec des horaires en journée et parfois les week-ends, nuits et en soirée.\r\n\r\nSalarié, chef d’entreprise ou indépendant, il gagne entre 2 000 € et 4 000 € bruts par mois, et jusqu’à plus de 8 000 € en fin de carrière.",
            "Le salaire d'un planneur stratégique dépend de la taille de l'entreprise pour laquelle il travaille, de l’ampleur des projets menés et de son expérience. On observe aussi des salaires plus élevés en Île-de-France qu'en région.",
            "Qualités majeures\r\n\r\nForte sensibilité à l’air du temps, curiosité, ouverture d’esprit, esprit créatif et imagination : voilà les cinq qualités phares du planneur stratégique.\r\n\r\nPour mieux « sentir » son époque, il doit aussi faire montre d’une excellente culture générale, qu’il cultive via l'art, la culture, l'économie ou la littérature.\r\n\r\nPour construire des analyses précises et fiables, il doit être rigoureux et synthétique. Il sait s’exprimer parfaitement, à l’écrit comme à l’oral et détient une culture marketing – y compris digitale – étendue.\r\n\r\nAmené à travailler au quotidien en équipe, il fait preuve d’un excellent relationnel.\r\n\r\nTravaillant parfois dans l’urgence, il doit être réactif et adaptable. Il pratique a minima un anglais courant.\r\n\r\nExpérience\r\n\r\nOn ne devient pas planneur stratégique au sortir des études. Généralement, on accède à la fonction après 3 à 5 ans dans des fonctions commerciales ou créatives (agences médias, annonceurs, régies publicitaires).\r\n\r\nEn début de carrière, les stages permettent d'acquérir de premières expériences qui faciliteront l'insertion professionnelle par la suite.",
            "En agence ou chez l’annonceur, le planneur stratégique peut évoluer vers le poste de responsable ou directeur du planning stratégique, lorsqu’il existe."
        ]

        # Call the method under test
        unique_strings = DrupalJsonApiClient.remove_redundant_strings_based_on_similarity_threshold(phrases=strings, similarity_threshold=0.30)

        # Assertions to verify that no strings are removed since they are complementary
        assert len(unique_strings) == len(strings)
        for string in strings:
            assert string in unique_strings

    def test_remove_redundant_str_should_not_remove_when_no_duplicates(self):
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




