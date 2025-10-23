"""End-to-end tests for complete user flow through the API

This test module verifies the complete user journey through the SkillForge API:
1. User sets their information (/user/set-infos)
2. User sets their preferences (/user/preferences)
3. User activates the service (/user/activate-service)
4. User gets thread IDs for a context (/thread/get-all/ids)
5. User asks a query in a thread (/thread/{thread_id}/query)
6. User retrieves messages from the thread (/thread/{thread_id}/messages)
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from uuid import UUID
from security.auth_dependency import authentication_required
from security.jwt_skillforge_payload import JWTSkillForgePayload


class TestCompleteUserFlow:
    """End-to-end tests for complete user flow through the API"""

    def _create_mock_auth_dependency(self, lms_user_id: int):
        """Create a mock authentication dependency that returns a JWT payload with the given LMS user ID"""

        async def mock_auth():
            return JWTSkillForgePayload(client=lms_user_id, exp=9999999999)

        return mock_auth

    def test_complete_user_flow_e2e(self, app: FastAPI, client: TestClient, mock_context_filter_request: dict):
        """Test complete user flow from registration to querying and retrieving messages"""
        # Arrange
        lms_user_id = 9001
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Step 1: Create/update user information
            user_data = {
                "lms_user_id": str(lms_user_id),
                "school_name": "E2E Test School",
                "civility": "Ms",
                "first_name": "Alice",
                "last_name": "Johnson",
                "email": "alice.johnson@example.com",
            }
            user_response = client.patch("/user/set-infos", json=user_data)

            # Assert Step 1
            assert user_response.status_code == 200
            user_data_response = user_response.json()
            assert user_data_response["first_name"] == "Alice"
            assert user_data_response["last_name"] == "Johnson"
            assert user_data_response["email"] == "alice.johnson@example.com"

            # Step 2: Set user preferences
            preferences_data = {"language": "en", "theme": "dark", "timezone": "UTC", "notifications_enabled": True, "email_notifications": False}
            preferences_response = client.patch("/user/preferences", json=preferences_data)

            # Assert Step 2
            assert preferences_response.status_code == 200
            preferences_response_data = preferences_response.json()
            assert preferences_response_data["status"] == "success"
            assert "preference_id" in preferences_response_data

            # Step 3: Activate the service
            activation_response = client.post("/user/activate-service")

            # Assert Step 3
            assert activation_response.status_code == 200
            assert activation_response.json() is True

            # Step 4: Get thread IDs (should create a new thread)
            thread_ids_response = client.post("/thread/get-all/ids", json=mock_context_filter_request)

            # Assert Step 4
            assert thread_ids_response.status_code == 200
            thread_ids_data = thread_ids_response.json()
            assert "threads_ids" in thread_ids_data
            assert len(thread_ids_data["threads_ids"]) == 1
            thread_id = thread_ids_data["threads_ids"][0]
            # Verify it's a valid UUID
            UUID(thread_id)

            # Step 5: Ask a query in the thread
            query_data = {
                "query": {"query_text_content": "What is machine learning and how does it work?", "query_selected_text": "", "query_quick_action": None, "query_attachments": None},
                "course_context": mock_context_filter_request,
            }
            query_response = client.post(f"/thread/{thread_id}/query", json=query_data)

            # Assert Step 5
            assert query_response.status_code == 200
            # Streaming response - verify we can read the content
            response_content = query_response.text
            assert len(response_content) > 0

            # Step 6: Retrieve messages from the thread
            messages_response = client.get(f"/thread/{thread_id}/messages")

            # Assert Step 6
            assert messages_response.status_code == 200
            messages_data = messages_response.json()
            assert messages_data["thread_id"] == thread_id
            assert "messages" in messages_data
            # Should have 2 messages: one from user, one from assistant
            assert messages_data["messages_count"] == 2
            assert len(messages_data["messages"]) == 2

            # Verify message structure
            user_message = messages_data["messages"][0]
            assert user_message["role"]["name"] == "user"
            assert user_message["content"] == "What is machine learning and how does it work?"

            assistant_message = messages_data["messages"][1]
            assert assistant_message["role"]["name"] == "assistant"
            assert len(assistant_message["content"]) > 0

        finally:
            app.dependency_overrides.clear()

    def test_complete_flow_with_multiple_queries(self, app: FastAPI, client: TestClient, mock_context_filter_video: dict):
        """Test complete flow with multiple queries in the same thread"""
        # Arrange
        lms_user_id = 9002
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Step 1: Create user
            user_data = {
                "lms_user_id": str(lms_user_id),
                "school_name": "E2E Multi Query Test School",
                "civility": "Mr",
                "first_name": "Bob",
                "last_name": "Smith",
                "email": "bob.smith@example.com",
            }
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Step 2: Set preferences
            preferences_data = {"language": "fr", "theme": "light", "notifications_enabled": True}
            preferences_response = client.patch("/user/preferences", json=preferences_data)
            assert preferences_response.status_code == 200

            # Step 3: Activate service
            activation_response = client.post("/user/activate-service")
            assert activation_response.status_code == 200

            # Step 4: Get thread IDs
            thread_ids_response = client.post("/thread/get-all/ids", json=mock_context_filter_video)
            assert thread_ids_response.status_code == 200
            thread_id = thread_ids_response.json()["threads_ids"][0]

            # Step 5: Ask multiple queries
            queries = ["Explain the video content", "What are the key concepts?", "Can you summarize the main points?"]

            for query_text in queries:
                query_data = {
                    "query": {"query_text_content": query_text, "query_selected_text": "", "query_quick_action": None, "query_attachments": None},
                    "course_context": mock_context_filter_video,
                }
                query_response = client.post(f"/thread/{thread_id}/query", json=query_data)
                assert query_response.status_code == 200

            # Step 6: Retrieve all messages
            messages_response = client.get(f"/thread/{thread_id}/messages")
            assert messages_response.status_code == 200

            messages_data = messages_response.json()
            # Should have 6 messages: 3 user queries + 3 assistant responses
            assert messages_data["messages_count"] == 6
            assert len(messages_data["messages"]) == 6

            # Verify alternating user/assistant pattern
            for i, message in enumerate(messages_data["messages"]):
                expected_role = "user" if i % 2 == 0 else "assistant"
                assert message["role"]["name"] == expected_role

        finally:
            app.dependency_overrides.clear()

    def test_complete_flow_with_pagination(self, app: FastAPI, client: TestClient, mock_context_filter_pdf: dict):
        """Test complete flow with message pagination"""
        # Arrange
        lms_user_id = 9003
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Step 1: Create user
            user_data = {
                "lms_user_id": str(lms_user_id),
                "school_name": "E2E Pagination Test School",
                "civility": "Dr",
                "first_name": "Carol",
                "last_name": "Williams",
                "email": "carol.williams@example.com",
            }
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Step 2: Set preferences
            preferences_data = {"language": "es", "theme": "auto"}
            preferences_response = client.patch("/user/preferences", json=preferences_data)
            assert preferences_response.status_code == 200

            # Step 3: Activate service
            activation_response = client.post("/user/activate-service")
            assert activation_response.status_code == 200

            # Step 4: Get thread IDs
            thread_ids_response = client.post("/thread/get-all/ids", json=mock_context_filter_pdf)
            assert thread_ids_response.status_code == 200
            thread_id = thread_ids_response.json()["threads_ids"][0]

            # Step 5: Add 4 queries (8 messages total: 4 user + 4 assistant)
            for i in range(4):
                query_data = {
                    "query": {"query_text_content": f"Question {i + 1} about the PDF", "query_selected_text": "", "query_quick_action": None, "query_attachments": None},
                    "course_context": mock_context_filter_pdf,
                }
                # Consume the streaming response to persist the assistant message
                with client.stream("POST", f"/thread/{thread_id}/query", json=query_data) as response:
                    assert response.status_code == 200
                    # Consume the stream
                    b"".join(response.iter_bytes())

            # Step 6: Retrieve messages with pagination
            # With reverse pagination: page 1 returns the MOST RECENT messages
            # Total 8 messages in chronological order: Q1, A1, Q2, A2, Q3, A3, Q4, A4 (indices 0-7)

            # Get first page (3 messages) - offset = max(0, 8 - 1*3) = 5, limit 3 → messages at indices 5, 6, 7: A3, Q4, A4
            page1_response = client.get(f"/thread/{thread_id}/messages?page_number=1&page_size=3")
            assert page1_response.status_code == 200
            page1_data = page1_response.json()
            assert page1_data["messages_count"] == 8
            assert len(page1_data["messages"]) == 3

            # Verify page 1 contains the MOST RECENT messages in chronological order: A3, Q4, A4
            page1_messages = page1_data["messages"]
            assert page1_messages[0]["role"]["name"] == "assistant", "Page 1, message 0 should be assistant (A3)"
            assert page1_messages[1]["role"]["name"] == "user", "Page 1, message 1 should be user (Q4)"
            assert "Question 4" in page1_messages[1]["content"], "Page 1, message 1 should be 'Question 4'"
            assert page1_messages[2]["role"]["name"] == "assistant", "Page 1, message 2 should be assistant (A4)"
            # Verify these are the most recent by checking they come after Q3
            assert "Question 3" not in page1_messages[1]["content"], "Page 1 should not contain Q3"

            # Get second page (3 messages) - offset = max(0, 8 - 2*3) = 2, limit 3 → messages at indices 2, 3, 4: Q2, A2, Q3
            page2_response = client.get(f"/thread/{thread_id}/messages?page_number=2&page_size=3")
            assert page2_response.status_code == 200
            page2_data = page2_response.json()
            assert page2_data["messages_count"] == 8
            assert len(page2_data["messages"]) == 3

            # Verify page 2 contains the MIDDLE messages in chronological order: Q2, A2, Q3
            page2_messages = page2_data["messages"]
            assert page2_messages[0]["role"]["name"] == "user", "Page 2, message 0 should be user (Q2)"
            assert "Question 2" in page2_messages[0]["content"], "Page 2, message 0 should be 'Question 2'"
            assert page2_messages[1]["role"]["name"] == "assistant", "Page 2, message 1 should be assistant (A2)"
            assert page2_messages[2]["role"]["name"] == "user", "Page 2, message 2 should be user (Q3)"
            assert "Question 3" in page2_messages[2]["content"], "Page 2, message 2 should be 'Question 3'"

            # Get third page (3 messages) - offset = max(0, 8 - 3*3) = 0, limit 3 → messages at indices 0, 1, 2: Q1, A1, Q2
            page3_response = client.get(f"/thread/{thread_id}/messages?page_number=3&page_size=3")
            assert page3_response.status_code == 200
            page3_data = page3_response.json()
            assert page3_data["messages_count"] == 8
            assert len(page3_data["messages"]) == 3

            # Verify page 3 contains the OLDEST messages in chronological order: Q1, A1, Q2
            page3_messages = page3_data["messages"]
            assert page3_messages[0]["role"]["name"] == "user", "Page 3, message 0 should be user (Q1)"
            assert "Question 1" in page3_messages[0]["content"], "Page 3, message 0 should be 'Question 1' (oldest)"
            assert page3_messages[1]["role"]["name"] == "assistant", "Page 3, message 1 should be assistant (A1)"
            assert page3_messages[2]["role"]["name"] == "user", "Page 3, message 2 should be user (Q2)"
            assert "Question 2" in page3_messages[2]["content"], "Page 3, message 2 should be 'Question 2'"

            # Verify chronological order within each page by checking timestamps
            from datetime import datetime

            for page_num, page_data in enumerate([page1_data, page2_data, page3_data], start=1):
                messages = page_data["messages"]
                if len(messages) > 1:
                    timestamps = [datetime.fromisoformat(msg["created_at"]) for msg in messages]
                    assert timestamps == sorted(timestamps), f"Page {page_num}: Messages should be in chronological order (oldest to newest)"

            # Verify that page 1's first message is NEWER than or equal to page 2's last message (reverse pagination works)
            # Note: Using >= instead of > because messages can have identical timestamps due to microsecond precision
            page1_first_timestamp = datetime.fromisoformat(page1_messages[0]["created_at"])
            page2_last_timestamp = datetime.fromisoformat(page2_messages[-1]["created_at"])
            assert page1_first_timestamp >= page2_last_timestamp, "Page 1 (most recent) should contain messages newer than or equal to page 2"

            # Verify that page 2's first message is NEWER than or equal to page 3's last message
            page2_first_timestamp = datetime.fromisoformat(page2_messages[0]["created_at"])
            page3_last_timestamp = datetime.fromisoformat(page3_messages[-1]["created_at"])
            assert page2_first_timestamp >= page3_last_timestamp, "Page 2 should contain messages newer than or equal to page 3 (oldest)"

        finally:
            app.dependency_overrides.clear()

    def test_complete_flow_different_contexts(self, app: FastAPI, client: TestClient, mock_context_filter_request: dict, mock_context_filter_video: dict):
        """Test complete flow with different course contexts (should create separate threads)"""
        # Arrange
        lms_user_id = 9004
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Step 1: Create user
            user_data = {
                "lms_user_id": str(lms_user_id),
                "school_name": "E2E Multi Context Test School",
                "civility": "Mr",
                "first_name": "David",
                "last_name": "Brown",
                "email": "david.brown@example.com",
            }
            user_response = client.patch("/user/set-infos", json=user_data)
            assert user_response.status_code == 200

            # Step 2: Set preferences
            preferences_data = {"language": "en", "theme": "dark"}
            preferences_response = client.patch("/user/preferences", json=preferences_data)
            assert preferences_response.status_code == 200

            # Step 3: Activate service
            activation_response = client.post("/user/activate-service")
            assert activation_response.status_code == 200

            # Step 4a: Get thread IDs for first context
            thread_ids_response1 = client.post("/thread/get-all/ids", json=mock_context_filter_request)
            assert thread_ids_response1.status_code == 200
            thread_id1 = thread_ids_response1.json()["threads_ids"][0]

            # Step 5a: Ask query in first thread
            query_data1 = {
                "query": {"query_text_content": "Question about text resource", "query_selected_text": "", "query_quick_action": None, "query_attachments": None},
                "course_context": mock_context_filter_request,
            }
            query_response1 = client.post(f"/thread/{thread_id1}/query", json=query_data1)
            assert query_response1.status_code == 200

            # Step 4b: Get thread IDs for second context (should be different)
            thread_ids_response2 = client.post("/thread/get-all/ids", json=mock_context_filter_video)
            assert thread_ids_response2.status_code == 200
            thread_id2 = thread_ids_response2.json()["threads_ids"][0]

            # Verify different thread IDs
            assert thread_id1 != thread_id2

            # Step 5b: Ask query in second thread
            query_data2 = {
                "query": {"query_text_content": "Question about video resource", "query_selected_text": "", "query_quick_action": None, "query_attachments": None},
                "course_context": mock_context_filter_video,
            }
            query_response2 = client.post(f"/thread/{thread_id2}/query", json=query_data2)
            assert query_response2.status_code == 200

            # Step 6: Retrieve messages from both threads
            messages_response1 = client.get(f"/thread/{thread_id1}/messages")
            assert messages_response1.status_code == 200
            messages_data1 = messages_response1.json()
            assert messages_data1["messages_count"] == 2

            messages_response2 = client.get(f"/thread/{thread_id2}/messages")
            assert messages_response2.status_code == 200
            messages_data2 = messages_response2.json()
            assert messages_data2["messages_count"] == 2

            # Verify different content in each thread
            assert messages_data1["messages"][0]["content"] == "Question about text resource"
            assert messages_data2["messages"][0]["content"] == "Question about video resource"

        finally:
            app.dependency_overrides.clear()
