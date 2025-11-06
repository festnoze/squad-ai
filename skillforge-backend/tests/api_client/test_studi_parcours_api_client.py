"""
Unit tests for StudiParcoursApiClient.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api_client.models.parcours_hierarchy_models import ParcoursHierarchy
from api_client.studi_parcours_api_client import StudiParcoursApiClient, StudiParcoursApiClientException


class TestStudiParcoursApiClient:
    """Test suite for StudiParcoursApiClient."""

    @pytest.fixture
    def client(self) -> StudiParcoursApiClient:
        """Create a client instance for testing."""
        return StudiParcoursApiClient(jwt_token="test-jwt-token", base_url="https://test-api.example.com", timeout=10.0)

    @pytest.fixture
    def mock_hierarchy_response(self) -> dict[str, Any]:
        """Create a mock hierarchy response matching the API structure."""
        return {
            "id": 123,
            "code": "PARC-001",
            "titre": "Test Parcours",
            "publication_date": "2024-01-01T00:00:00Z",
            "archived": False,
            "parcours_json": "parcours_123.json",
            "blocs": [
                {
                    "id": 1,
                    "code": "BLOC-001",
                    "libelle": "Test Bloc",
                    "ordre": 1,
                    "coefficient": 1.5,
                    "blocId": 10,
                    "is_option": False,
                    "linkedElementId": None,
                    "evaluations": [
                        {
                            "id": 100,
                            "code": "EVAL-001",
                            "titre": "Test Evaluation",
                            "categorie": "Test Category",
                            "ordre": 1,
                            "coefficient": 2.0,
                            "status": "active",
                            "evaluationTypeId": 5,
                            "notRated": False,
                            "infoNote": True,
                            "deliveryNote": True,
                            "deliveryCopy": False,
                            "deliveryCorrectionType": True,
                            "useModel": False,
                            "isResitEvaluation": False,
                            "linkEvaluationGrid": None,
                            "legalTitleName": None,
                            "modeEnonceId": None,
                            "examSessionId": None,
                            "examSessionStartDate": None,
                            "examSessionEndDate": None,
                            "codelaiReservationde": None,
                            "remiseDocumentsObligatoire": None,
                            "autorisationEleveInscriptionOral": None,
                            "modules": [{"id": 200, "code": "MOD-001", "titre": "Test Module", "duree": 60}],
                        }
                    ],
                }
            ],
            "matieres": [
                {
                    "id": 1,
                    "code": "MAT-001",
                    "titre": "Test Matiere",
                    "description": "Test Description",
                    "ordre": 1,
                    "duree": 120,
                    "ponderation_debut": 0,
                    "ponderation_fin": 100,
                    "elementId": 20,
                    "is_option": False,
                    "planning": True,
                    "linkedEvaluationsBlocksIds": [1, 2],
                    "modules": [
                        {
                            "id": 10,
                            "code": "MOD-MAT-001",
                            "titre": "Test Module Matiere",
                            "description": "Module Description",
                            "ordre": 1,
                            "duree": 60,
                            "ponderation_debut": 0,
                            "ponderation_fin": 50,
                            "type": "standard",
                            "themes": [
                                {
                                    "id": 50,
                                    "code": "THEME-001",
                                    "titre": "Test Theme",
                                    "description": "Theme Description",
                                    "ordre": 1,
                                    "duree": 30,
                                    "ressources": [
                                        {
                                            "id": 500,
                                            "titre": "Test Resource",
                                            "categorie": "video",
                                            "ordre": 1,
                                            "duree": 15,
                                            "difficulty": 2,
                                            "priority": "high",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "examens": [{"id": 1000, "name": "Test Exam", "examenTypeId": 3}],
                }
            ],
            "examens": [{"id": 2000, "name": "Final Exam", "examenTypeId": 5}],
        }

    async def test_aget_parcours_hierarchy_success_async(self, client: StudiParcoursApiClient, mock_hierarchy_response: dict[str, Any]) -> None:
        """Test successful retrieval of parcours hierarchy."""
        # Mock the httpx.AsyncClient
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_hierarchy_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Call the method
            result = await client.aget_parcours_hierarchy(parcours_id=123, use_cache=False)

            # Assertions
            assert isinstance(result, ParcoursHierarchy)
            assert result.id == 123
            assert result.code == "PARC-001"
            assert result.titre == "Test Parcours"
            assert len(result.blocs) == 1
            assert len(result.matieres) == 1
            assert len(result.examens) == 1

            # Verify nested structure
            assert result.blocs[0].libelle == "Test Bloc"
            assert len(result.blocs[0].evaluations) == 1
            assert result.matieres[0].titre == "Test Matiere"
            assert len(result.matieres[0].modules) == 1
            assert len(result.matieres[0].modules[0].themes) == 1
            assert len(result.matieres[0].modules[0].themes[0].ressources) == 1

            # Verify the API was called correctly
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "123/hierarchy" in call_args[0][0]
            assert call_args[1]["params"]["useCache"] == "false"

    async def test_aget_parcours_hierarchy_with_cache_async(self, client: StudiParcoursApiClient, mock_hierarchy_response: dict[str, Any]) -> None:
        """Test parcours hierarchy retrieval with cache enabled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_hierarchy_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Call with cache enabled
            result = await client.aget_parcours_hierarchy(parcours_id=456, use_cache=True)

            # Verify the API was called with cache parameter
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["useCache"] == "true"
            assert isinstance(result, ParcoursHierarchy)

    async def test_aget_parcours_hierarchy_http_error_async(self, client: StudiParcoursApiClient) -> None:
        """Test handling of HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Parcours not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Should raise StudiParcoursApiClientException
            with pytest.raises(StudiParcoursApiClientException) as exc_info:
                await client.aget_parcours_hierarchy(parcours_id=999)

            assert "HTTP error occurred" in str(exc_info.value)
            assert "404" in str(exc_info.value)

    async def test_aget_parcours_hierarchy_request_error_async(self, client: StudiParcoursApiClient) -> None:
        """Test handling of network/request errors."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
            mock_client_class.return_value = mock_client

            # Should raise StudiParcoursApiClientException
            with pytest.raises(StudiParcoursApiClientException) as exc_info:
                await client.aget_parcours_hierarchy(parcours_id=123)

            assert "Request error occurred" in str(exc_info.value)

    async def test_aget_parcours_hierarchy_invalid_json_async(self, client: StudiParcoursApiClient) -> None:
        """Test handling of invalid JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Should raise StudiParcoursApiClientException
            with pytest.raises(StudiParcoursApiClientException) as exc_info:
                await client.aget_parcours_hierarchy(parcours_id=123)

            assert "Failed to parse API response" in str(exc_info.value)

    async def test_aget_parcours_hierarchy_json_success_async(self, client: StudiParcoursApiClient, mock_hierarchy_response: dict[str, Any]) -> None:
        """Test successful retrieval of raw JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(mock_hierarchy_response)
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Call the JSON method
            result = await client.aget_parcours_hierarchy_json(parcours_id=123)

            # Verify result is raw JSON string
            assert isinstance(result, str)
            parsed = json.loads(result)
            assert parsed["id"] == 123
            assert parsed["code"] == "PARC-001"

    def test_client_initialization(self) -> None:
        """Test client initialization with different parameters."""
        # With custom parameters
        client1 = StudiParcoursApiClient(jwt_token="custom-token", base_url="https://custom.api.com", timeout=60.0)
        assert client1.base_url == "https://custom.api.com"
        assert client1.jwt_token == "custom-token"
        assert client1.timeout == 60.0

        # Test trailing slash removal
        client2 = StudiParcoursApiClient(jwt_token="token", base_url="https://api.com/")
        assert client2.base_url == "https://api.com"

    def test_get_headers(self) -> None:
        """Test headers generation."""
        client = StudiParcoursApiClient(jwt_token="test-jwt-token", base_url="https://test.com")
        headers = client._get_headers()

        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" in headers
        assert "Bearer test-jwt-token" in headers["Authorization"]

    def test_get_headers_without_jwt_token(self) -> None:
        """Test headers generation without JWT token."""
        client = StudiParcoursApiClient(base_url="https://test.com")
        headers = client._get_headers()

        assert "Authorization" not in headers

    def test_get_headers_with_per_request_token(self) -> None:
        """Test headers generation with per-request JWT token override."""
        client = StudiParcoursApiClient(jwt_token="instance-token", base_url="https://test.com")

        # Use instance token
        headers1 = client._get_headers()
        assert "Bearer instance-token" in headers1["Authorization"]

        # Override with per-request token
        headers2 = client._get_headers(jwt_token="request-token")
        assert "Bearer request-token" in headers2["Authorization"]
