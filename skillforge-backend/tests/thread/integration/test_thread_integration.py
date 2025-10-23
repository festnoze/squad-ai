"""Integration tests for Thread feature (endpoint -> service -> repository)

These tests verify the complete flow from HTTP request through service layer to repository,
using real database operations but with dependency overrides for authentication.
"""

from uuid import uuid4, UUID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security.auth_dependency import authentication_required
from application.thread_service import ThreadService
from security.jwt_skillforge_payload import JWTSkillForgePayload


class TestThreadIntegration:
    """Integration tests for complete thread flow"""

    def test_get_all_threads_ids_or_create_new_no_threads(self, app: FastAPI, client: TestClient, mock_context_filter_request: dict):
        """Test getting thread IDs when user has no threads - should return a new thread ID"""
        # Arrange - Create user first
        lms_user_id = 2001
        user_data = self._create_valid_user_data(2001)

        # Override authentication to return our test user
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Create user
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Act - Get thread IDs (should create new one)
            response = client.post("/thread/get-all/ids", json=mock_context_filter_request)

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert "threads_ids" in data
            assert len(data["threads_ids"]) == 1
            # Verify it's a valid UUID
            thread_id = UUID(data["threads_ids"][0])
            assert thread_id is not None
        finally:
            # Cleanup: remove override
            app.dependency_overrides.clear()

    def test_get_all_threads_ids_existing_threads(self, app: FastAPI, client: TestClient, mock_context_filter_video: dict):
        """Test getting thread IDs when user has existing threads for a context"""
        # Arrange - Create user first
        lms_user_id = 2002
        user_data = self._create_valid_user_data(2002)

        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Create user
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Get a thread ID
            response1 = client.post("/thread/get-all/ids", json=mock_context_filter_video)
            assert response1.status_code == 200
            assert len(response1.json()["threads_ids"]) == 1
            thread_id = response1.json()["threads_ids"][0]

            # Add a query to create the thread (this is needed to persist the thread)
            query_data = {"query": {"query_text_content": "What is this video about?", "query_selected_text": "", "query_quick_action": None, "query_attachments": None}, "course_context": mock_context_filter_video}
            query_response = client.post(f"/thread/{thread_id}/query", json=query_data)
            assert query_response.status_code == 200

            # Act - Get thread IDs again (should return the existing thread)
            response2 = client.post("/thread/get-all/ids", json=mock_context_filter_video)

            # Assert
            assert response2.status_code == 200
            data = response2.json()
            assert "threads_ids" in data
            assert len(data["threads_ids"]) == 1
            assert thread_id in data["threads_ids"]
        finally:
            app.dependency_overrides.clear()

    def test_get_thread_messages_empty_thread(self, app: FastAPI, client: TestClient):
        """Test getting messages from a thread that doesn't exist (should return empty thread)"""
        # Arrange
        lms_user_id = 2003
        user_data = self._create_valid_user_data(2003)

        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Create user
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Generate a random thread ID
            thread_id = str(uuid4())

            # Act - Get messages from non-existent thread
            response = client.get(f"/thread/{thread_id}/messages")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["thread_id"] == thread_id
            assert data["messages"] == []
            assert data["messages_count"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_add_query_to_new_thread(self, app: FastAPI, client: TestClient, mock_context_filter_pdf: dict):
        """Test adding a query to a non-existent thread - should create thread automatically"""
        # Arrange
        lms_user_id = 2004
        user_data = self._create_valid_user_data(2004)

        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Create user
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            query_data = {
                "query": {"query_text_content": "Explain this concept", "query_selected_text": "Some selected text", "query_quick_action": "explanation", "query_attachments": None},
                "course_context": mock_context_filter_pdf,
            }

            # Generate a new thread ID
            thread_id = str(uuid4())

            # Act - Add query to non-existent thread (should create it)
            response = client.post(f"/thread/{thread_id}/query", json=query_data)

            # Assert
            assert response.status_code == 200
            # Response is streaming, so we just verify it's successful
        finally:
            app.dependency_overrides.clear()

    def test_add_query_to_existing_thread(self, app: FastAPI, client: TestClient, mock_context_filter_request: dict):
        """Test adding multiple queries to the same thread"""
        # Arrange
        lms_user_id = 2005
        user_data = self._create_valid_user_data(2005)

        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Create user
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Get a thread ID
            response = client.post("/thread/get-all/ids", json=mock_context_filter_request)
            thread_id = response.json()["threads_ids"][0]

            # Act - Add multiple queries
            queries = ["What is machine learning?", "How does neural network work?", "Explain gradient descent"]

            for query_text in queries:
                query_data = {"query": {"query_text_content": query_text, "query_selected_text": "", "query_quick_action": None, "query_attachments": None}, "course_context": mock_context_filter_request}
                response = client.post(f"/thread/{thread_id}/query", json=query_data)
                assert response.status_code == 200

            # Verify messages were added
            messages_response = client.get(f"/thread/{thread_id}/messages")
            assert messages_response.status_code == 200
            data = messages_response.json()
            # Each query adds 2 messages (user + assistant)
            assert data["messages_count"] == len(queries) * 2
        finally:
            app.dependency_overrides.clear()

    def test_quota_exceeded(self, app: FastAPI, client: TestClient, test_thread_service: ThreadService, mock_context_filter_request: dict):
        """Test that quota is enforced when adding too many messages"""
        # Arrange
        lms_user_id = 2006
        user_data = self._create_valid_user_data(2006)

        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        # Set low quota for testing (allow 2 user messages)
        original_max = test_thread_service.max_messages_by_conversation
        max_user_messages = 2
        test_thread_service.max_messages_by_conversation = max_user_messages

        try:
            # Create user
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Get a thread ID
            response = client.post("/thread/get-all/ids", json=mock_context_filter_request)
            thread_id = response.json()["threads_ids"][0]

            # Act & Assert- Add queries up to the limit
            query_data: dict = {"query": {"query_text_content": "Query", "query_selected_text": "", "query_quick_action": None, "query_attachments": None}, "course_context": mock_context_filter_request}
            for i in range(1, max_user_messages + 1):
                query_data["query"]["query_text_content"] = f"Query {i}"
                with client.stream("POST", f"/thread/{thread_id}/query", json=query_data) as response:
                    assert response.status_code == 200

            # Act & Assert- Add query beyond the limit
            query_data["query"]["query_text_content"] = f"Query {i}"
            with client.stream("POST", f"/thread/{thread_id}/query", json=query_data) as response:
                assert response.status_code == 429, "User message count: 2 - Quota exceeded!"

        except Exception as e:
            print(f"Test failed with exception: {e}")
            raise
        finally:
            # Restore original max
            test_thread_service.max_messages_by_conversation = original_max
            app.dependency_overrides.clear()

    def test_get_thread_messages_with_pagination(self, app: FastAPI, client: TestClient, mock_context_filter_request: dict):
        """Test getting messages with pagination"""
        # Arrange
        lms_user_id = 2007
        user_data = self._create_valid_user_data(2007)

        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Create user
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Get a thread ID
            response = client.post("/thread/get-all/ids", json=mock_context_filter_request)
            thread_id = response.json()["threads_ids"][0]

            # Add 3 queries (6 messages total)
            for i in range(3):
                query_data = {"query": {"query_text_content": f"Query {i}", "query_selected_text": "", "query_quick_action": None, "query_attachments": None}, "course_context": mock_context_filter_request}
                # Need to consume the streaming response for the assistant message to be persisted
                with client.stream("POST", f"/thread/{thread_id}/query", json=query_data) as response:
                    # Consume the stream to trigger message persistence
                    b"".join(response.iter_bytes())

            # Act - Get messages with pagination
            response_page1 = client.get(f"/thread/{thread_id}/messages?page_number=1&page_size=2")
            response_page2 = client.get(f"/thread/{thread_id}/messages?page_number=2&page_size=2")

            # Assert
            assert response_page1.status_code == 200
            assert response_page2.status_code == 200

            page1_data = response_page1.json()
            page2_data = response_page2.json()

            assert page1_data["messages_count"] == 6
            assert len(page1_data["messages"]) == 2  # page_size=2
            assert len(page2_data["messages"]) == 2
        finally:
            app.dependency_overrides.clear()

    def _create_valid_user_data(self, lms_user_id: int, first_name: str = "Test", last_name: str = "User", email: str | None = None) -> dict:
        """Helper to create valid user data that matches UserInfosRequest schema

        Args:
            lms_user_id: Required unique LMS user ID
            first_name: User's first name (default: "Test")
            last_name: User's last name (default: "User")
            email: User's email (default: generated from lms_user_id)

        Note: Preferences are now set separately via /user/preferences endpoint
        """
        if email is None:
            email = f"user{lms_user_id}@test.com"

        return {
            "lms_user_id": str(lms_user_id),
            "school_name": "Test School",
            "civility": "Mr",
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
        }

    def _create_mock_auth_dependency(self, lms_user_id: int):
        """Create a mock authentication dependency that returns a JWT payload with the given LMS user ID"""

        async def mock_auth():
            return JWTSkillForgePayload(client=lms_user_id, exp=9999999999)

        return mock_auth
