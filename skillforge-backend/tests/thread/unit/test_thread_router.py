"""Unit tests for Thread Router"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

#
from application.thread_service import ThreadService
from application.exceptions.quota_exceeded_exception import QuotaExceededException
from models.thread import Thread
from models.message import Message
from models.role import Role
from dependency_injection_config import deps


class TestThreadRouter:
    """Unit tests for thread router endpoints"""

    @pytest.fixture
    def mock_thread_service(self) -> Mock:
        """Fixture providing a mocked ThreadService"""
        service = Mock()
        service.aget_threads_ids_by_user_and_context = AsyncMock()
        service.aget_thread_by_id_or_create = AsyncMock()
        service.aprepare_thread_for_query = AsyncMock()
        service._astream_llm_response_and_persist = Mock()
        return service

    def _create_mock_jwt_payload(self, lms_user_id: int | str):
        """Helper to create a mock JWT payload"""
        from security.jwt_skillforge_payload import JWTSkillForgePayload

        # Use client field which maps to user LMS ID
        # get_lms_user_id() returns str(client)
        try:
            client_id = int(lms_user_id) if isinstance(lms_user_id, str) else lms_user_id
        except ValueError:
            # For test cases with invalid IDs like "not_an_int", use a dummy value
            client_id = 99999
        mock_payload = JWTSkillForgePayload(client=client_id, exp=9999999999)
        return mock_payload

    @pytest.fixture
    def client(self, app: FastAPI, mock_thread_service: Mock) -> TestClient:
        """Fixture providing test client with mocked thread service"""
        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            yield TestClient(app)

    def test_aget_all_threads_ids_or_create_new_no_threads(self, app: FastAPI, mock_thread_service: Mock):
        """Test getting thread IDs when no threads exist - should return new UUID"""
        # Arrange
        lms_user_id = 1001
        new_thread_id = uuid4()
        mock_thread_service.aget_threads_ids_by_user_and_context = AsyncMock(return_value=[new_thread_id])

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            context_data = {
                "ressource": {
                    "ressource_id": "res_001",
                    "ressource_type": "text",
                    "ressource_code": "code_001",
                    "ressource_title": "Test Resource",
                    "ressource_url": "http://example.com",
                    "ressource_path": "/path/to/resource",
                },
                "theme_id": "theme_001",
                "module_id": "module_001",
                "matiere_id": "matiere_001",
                "parcour_id": "parcour_001",
            }

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                response = client.post("/thread/get-all/ids", json=context_data)

                # Assert
                assert response.status_code == 200
                data = response.json()
                assert "threads_ids" in data
                assert len(data["threads_ids"]) == 1
                mock_thread_service.aget_threads_ids_by_user_and_context.assert_called_once()

    def test_aget_all_threads_ids_or_create_new_with_existing_threads(self, app: FastAPI, mock_thread_service: Mock):
        """Test getting thread IDs when threads exist"""
        # Arrange
        lms_user_id = 1002
        existing_thread_ids = [uuid4(), uuid4()]
        mock_thread_service.aget_threads_ids_by_user_and_context = AsyncMock(return_value=existing_thread_ids)

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            context_data = {"ressource": None, "theme_id": "theme_002", "module_id": "module_002", "matiere_id": "matiere_002", "parcour_id": "parcour_002"}

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                response = client.post("/thread/get-all/ids", json=context_data)

                # Assert
                assert response.status_code == 200
                data = response.json()
                assert "threads_ids" in data
                assert len(data["threads_ids"]) == 2

    def test_aget_thread_messages_empty_thread(self, app: FastAPI, mock_thread_service: Mock):
        """Test getting messages from an empty thread"""
        # Arrange
        lms_user_id = 1004
        thread_id = uuid4()
        user_id = uuid4()
        empty_thread = Thread(id=thread_id, user_id=user_id, messages=[])

        mock_thread_service.aget_thread_by_id_or_create = AsyncMock(return_value=empty_thread)
        mock_thread_service.aget_thread_messages_count = AsyncMock(return_value=0)

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                response = client.get(f"/thread/{thread_id}/messages")

                # Assert
                assert response.status_code == 200
                data = response.json()
                assert data["thread_id"] == str(thread_id)
                assert data["messages"] == []
                assert data["messages_count"] == 0

    def test_aget_thread_messages_with_messages(self, app: FastAPI, mock_thread_service: Mock):
        """Test getting messages from a thread with messages"""
        # Arrange
        lms_user_id = 1005
        thread_id = uuid4()
        user_id = uuid4()

        user_role = Role(id=uuid4(), name="user")
        assistant_role = Role(id=uuid4(), name="assistant")

        from datetime import datetime

        now = datetime.now()

        messages = [
            Message(id=uuid4(), thread_id=thread_id, role=user_role, content="User message", created_at=now),
            Message(id=uuid4(), thread_id=thread_id, role=assistant_role, content="Assistant response", created_at=now),
        ]

        thread_with_messages = Thread(id=thread_id, user_id=user_id, created_at=now, messages=messages)

        mock_thread_service.aget_thread_by_id_or_create = AsyncMock(return_value=thread_with_messages)
        mock_thread_service.aget_thread_messages_count = AsyncMock(return_value=2)

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                response = client.get(f"/thread/{thread_id}/messages")

                # Assert
                assert response.status_code == 200
                data = response.json()
                assert len(data["messages"]) == 2
                assert data["messages_count"] == 2

    def test_aget_thread_messages_with_pagination(self, app: FastAPI, mock_thread_service: Mock):
        """Test getting messages with pagination - page 1 should return last 5 messages in chronological order"""
        # Arrange
        lms_user_id = 1006
        thread_id = uuid4()
        user_id = uuid4()

        user_role = Role(id=uuid4(), name="user")

        from datetime import datetime

        now = datetime.now()

        # Mock the service to return only the last 5 messages (messages 5-9) in chronological order
        # This simulates the database-level pagination where page 1 returns the most recent messages
        paginated_messages = [Message(id=uuid4(), thread_id=thread_id, role=user_role, content=f"Message {i}", created_at=now) for i in range(5, 10)]

        thread_with_paginated_messages = Thread(id=thread_id, user_id=user_id, created_at=now, messages=paginated_messages)

        mock_thread_service.aget_thread_by_id_or_create = AsyncMock(return_value=thread_with_paginated_messages)
        mock_thread_service.aget_thread_messages_count = AsyncMock(return_value=10)  # Total of 10 messages

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                response = client.get(f"/thread/{thread_id}/messages?page_number=1&page_size=5")

                # Assert
                assert response.status_code == 200
                data = response.json()
                assert len(data["messages"]) == 5
                assert data["messages_count"] == 10  # Total messages, not just the paginated count
                # Verify the service was called with the correct pagination parameters
                assert mock_thread_service.aget_thread_by_id_or_create.call_count == 1
                call_args = mock_thread_service.aget_thread_by_id_or_create.call_args
                assert call_args.args[0] == thread_id  # First arg is thread_id
                assert call_args.kwargs["persist_thread_if_created"] is False
                assert call_args.kwargs["page_number"] == 1
                assert call_args.kwargs["page_size"] == 5

    def test_aget_thread_messages_invalid_thread_id(self, app: FastAPI, mock_thread_service: Mock):
        """Test getting messages with invalid thread ID"""
        # Arrange
        lms_user_id = 1007
        invalid_thread_id = "not-a-uuid"

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                response = client.get(f"/thread/{invalid_thread_id}/messages")

                # Assert
                assert response.status_code == 400

    def test_aanswer_user_query_into_thread_success(self, app: FastAPI, mock_thread_service: Mock):
        """Test successfully adding query to thread"""
        # Arrange
        lms_user_id = 123
        thread_id = uuid4()
        user_id = uuid4()

        # Create a mock thread that will be returned by aprepare_thread_for_query
        mock_thread = Thread(id=thread_id, user_id=user_id, messages=[])

        async def mock_generator():
            yield b"Response chunk 1"
            yield b"Response chunk 2"

        # Mock the preparation method
        mock_thread_service.aprepare_thread_for_query = AsyncMock(return_value=mock_thread)
        # Mock the streaming method
        mock_thread_service._astream_llm_response_and_persist = Mock(side_effect=lambda *args, **kwargs: mock_generator())

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            query_data = {
                "query": {"query_text_content": "What is AI?", "query_selected_text": "", "query_quick_action": None, "query_attachments": None},
                "course_context": {"ressource": None, "theme_id": "theme_001", "module_id": "module_001", "matiere_id": "matiere_001", "parcour_id": "parcour_001"},
            }

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act - Use stream to properly consume streaming response
                with client.stream("POST", f"/thread/{thread_id}/query", json=query_data) as response:
                    # Assert
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers["content-type"]

                    # Read and verify the streaming content
                    content = b"".join(response.iter_bytes())
                    assert content == b"Response chunk 1Response chunk 2"

                # Verify service methods were called
                mock_thread_service.aprepare_thread_for_query.assert_called_once()
                mock_thread_service._astream_llm_response_and_persist.assert_called_once_with(mock_thread)

    def test_aanswer_user_query_into_thread_invalid_thread_id(self, app: FastAPI, mock_thread_service: Mock):
        """Test adding query with invalid thread ID"""
        # Arrange
        lms_user_id = 123
        invalid_thread_id = "not-a-uuid"

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            query_data = {"query": {"query_text_content": "What is AI?", "query_selected_text": "", "query_quick_action": None, "query_attachments": None}, "course_context": {"ressource": None, "theme_id": "theme_001"}}

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                with client.stream("POST", f"/thread/{invalid_thread_id}/query", json=query_data) as response:
                    # Assert
                    assert response.status_code == 400

    def test_aanswer_user_query_into_thread_quota_exceeded(self, app: FastAPI, mock_thread_service: Mock):
        """Test adding query when quota is exceeded

        With the new architecture, the exception is raised in aprepare_thread_for_query
        BEFORE creating the StreamingResponse, so middleware can catch it and return HTTP 429.
        """
        # Arrange
        lms_user_id = 123
        thread_id = uuid4()

        # Mock the preparation method to raise QuotaExceededException
        mock_thread_service.aprepare_thread_for_query = AsyncMock(side_effect=QuotaExceededException("Quota exceeded"))

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service
            client = TestClient(app)

            query_data = {"query": {"query_text_content": "What is AI?", "query_selected_text": "", "query_quick_action": None, "query_attachments": None}, "course_context": {"ressource": None, "theme_id": "theme_001"}}

            # Mock authentication
            with patch("facade.thread_router.authentication_required") as mock_auth:
                mock_auth.return_value = self._create_mock_jwt_payload(lms_user_id)

                # Act
                response = client.post(f"/thread/{thread_id}/query", json=query_data)

                # Assert
                assert response.status_code == 429  # Too Many Requests
                data = response.json()
                assert data["status"] == "error"
                assert "Quota exceeded" in data["detail"]

    def test_aanswer_user_query_into_thread_invalid_lms_id(self, app: FastAPI, mock_thread_service: Mock):
        """Test adding query with invalid LMS user ID"""
        # Arrange
        thread_id = uuid4()

        with deps.override_for_test() as test_container:
            test_container[ThreadService] = mock_thread_service

            query_data = {"query": {"query_text_content": "What is AI?", "query_selected_text": "", "query_quick_action": None, "query_attachments": None}, "course_context": {"ressource": None, "theme_id": "theme_001"}}

            # Mock authentication with a JWT payload that has None as client
            # This will cause get_lms_user_id() to return "None" which is not a valid int
            from security.jwt_skillforge_payload import JWTSkillForgePayload
            from security.auth_dependency import authentication_required

            async def mock_authentication_required():
                return JWTSkillForgePayload(client=None, exp=9999999999)

            # Override the authentication dependency
            app.dependency_overrides[authentication_required] = mock_authentication_required

            try:
                client = TestClient(app)

                # Act
                response = client.post(f"/thread/{thread_id}/query", json=query_data)

                # Assert
                assert response.status_code == 400
            finally:
                # Clean up dependency override
                app.dependency_overrides.clear()
