"""Unit tests for JWT Helper module.

This module tests JWT token creation, encoding, decoding, and validation.
"""

import pytest
import jwt
import base64
from datetime import datetime, timedelta
from unittest.mock import patch
from security.jwt_helper import JWTHelper
from security.jwt_skillforge_payload import JWTSkillForgePayload


class TestJWTTokenCreation:
    """Tests for JWT token creation."""

    def test_create_token_success_async(self):
        """Test successful token creation with valid parameters."""
        # Arrange
        client = 199520
        school_id = 1009
        issuer = "uat-lms-studi.studi.fr"
        expires_in_hours = 24

        # Act
        token = JWTHelper.acreate_token(client, school_id, issuer, expires_in_hours)

        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_returns_base64_encoded_async(self):
        """Test that created token is base64 encoded."""
        # Arrange
        client = 199520
        school_id = 1009
        issuer = "test-issuer"
        expires_in_hours = 1

        # Act
        token = JWTHelper.acreate_token(client, school_id, issuer, expires_in_hours)

        # Assert - should be able to decode from base64 without errors
        try:
            decoded_bytes = base64.b64decode(token)
            jwt_token = decoded_bytes.decode("utf-8")
            assert jwt_token.startswith("eyJ")  # JWT tokens start with "eyJ"
        except Exception as e:
            pytest.fail(f"Token is not valid base64: {e}")

    def test_create_token_contains_correct_claims_async(self):
        """Test that created token contains all required claims."""
        # Arrange
        client = 199520
        school_id = 1009
        issuer = "test-issuer"
        expires_in_hours = 24

        # Act
        token = JWTHelper.acreate_token(client, school_id, issuer, expires_in_hours)
        payload = JWTHelper.adecode_token(token, verify_signature=False)

        # Assert
        assert payload.client == client
        assert payload.schoolId == school_id
        assert payload.iss == issuer
        assert payload.sid is not None
        assert payload.exp is not None
        assert payload.nbf is not None

    def test_create_token_generates_unique_sid_async(self):
        """Test that each token gets a unique session ID."""
        # Arrange
        client = 199520
        school_id = 1009
        issuer = "test-issuer"

        # Act
        token1 = JWTHelper.acreate_token(client, school_id, issuer, 1)
        token2 = JWTHelper.acreate_token(client, school_id, issuer, 1)

        payload1 = JWTHelper.adecode_token(token1, verify_signature=False)
        payload2 = JWTHelper.adecode_token(token2, verify_signature=False)

        # Assert
        assert payload1.sid != payload2.sid

    def test_create_token_expiration_time_async(self):
        """Test that token expiration is set correctly."""
        # Arrange
        client = 199520
        school_id = 1009
        issuer = "test-issuer"
        expires_in_hours = 24

        # Act
        before_creation = datetime.now()
        token = JWTHelper.acreate_token(client, school_id, issuer, expires_in_hours)
        after_creation = datetime.now()

        payload = JWTHelper.adecode_token(token, verify_signature=False)

        # Assert
        expected_exp_min = int((before_creation + timedelta(hours=expires_in_hours)).timestamp())
        expected_exp_max = int((after_creation + timedelta(hours=expires_in_hours)).timestamp())

        assert payload.exp is not None
        assert expected_exp_min <= payload.exp <= expected_exp_max


class TestJWTTokenDecoding:
    """Tests for JWT token decoding with various formats."""

    @pytest.fixture
    def sample_token(self):
        """Create a sample token for testing."""
        return JWTHelper.acreate_token(client=199520, school_id=1009, issuer="test-issuer", expires_in_hours=24)

    def test_decode_token_with_base64_only_async(self, sample_token):
        """Test decoding a token that is only base64 encoded (no Bearer prefix)."""
        # Act
        payload = JWTHelper.adecode_token(sample_token, verify_signature=False)

        # Assert
        assert payload is not None
        assert isinstance(payload, JWTSkillForgePayload)
        assert payload.client == 199520
        assert payload.schoolId == 1009

    def test_decode_token_with_bearer_prefix_uppercase_async(self, sample_token):
        """Test decoding a token with 'Bearer ' prefix (uppercase)."""
        # Arrange
        token_with_prefix = f"Bearer {sample_token}"

        # Act
        payload = JWTHelper.adecode_token(token_with_prefix, verify_signature=False)

        # Assert
        assert payload is not None
        assert payload.client == 199520
        assert payload.schoolId == 1009

    def test_decode_token_with_bearer_prefix_lowercase_async(self, sample_token):
        """Test decoding a token with 'bearer ' prefix (lowercase)."""
        # Arrange
        token_with_prefix = f"bearer {sample_token}"

        # Act
        payload = JWTHelper.adecode_token(token_with_prefix, verify_signature=False)

        # Assert
        assert payload is not None
        assert payload.client == 199520

    def test_decode_token_with_bearer_prefix_mixed_case_async(self, sample_token):
        """Test decoding a token with 'BeArEr ' prefix (mixed case)."""
        # Arrange
        token_with_prefix = f"BeArEr {sample_token}"

        # Act
        payload = JWTHelper.adecode_token(token_with_prefix, verify_signature=False)

        # Assert
        assert payload is not None
        assert payload.client == 199520

    def test_decode_token_with_whitespace_async(self, sample_token):
        """Test decoding a token with leading/trailing whitespace."""
        # Arrange
        token_with_whitespace = f"  {sample_token}  "

        # Act
        payload = JWTHelper.adecode_token(token_with_whitespace, verify_signature=False)

        # Assert
        assert payload is not None
        assert payload.client == 199520

    def test_decode_token_with_bearer_and_whitespace_async(self, sample_token):
        """Test decoding a token with Bearer prefix and whitespace."""
        # Arrange
        token_with_all = f"  Bearer {sample_token}  "

        # Act
        payload = JWTHelper.adecode_token(token_with_all, verify_signature=False)

        # Assert
        assert payload is not None
        assert payload.client == 199520

    def test_decode_raw_jwt_without_base64_fails_async(self):
        """Test that decoding a raw JWT (not base64 encoded) fails appropriately."""
        # Arrange - create a raw JWT token without base64 encoding
        import jwt as pyjwt
        from envvar import EnvHelper

        secret_key = EnvHelper.get_jwt_secret_key()
        algorithm = EnvHelper.get_jwt_algorithm()

        payload = {
            "sid": "test-sid",
            "client": 199520,
            "schoolId": 1009,
            "iss": "test-issuer",
            "exp": int((datetime.now() + timedelta(hours=1)).timestamp()),
            "nbf": int(datetime.now().timestamp()),
        }

        raw_jwt = pyjwt.encode(payload, secret_key, algorithm=algorithm)

        # Act & Assert - should fail because it's not base64 encoded
        with pytest.raises(ValueError, match="Invalid base64-encoded token"):
            JWTHelper.adecode_token(raw_jwt, verify_signature=False)


class TestJWTSignatureValidation:
    """Tests for JWT signature validation."""

    def test_decode_with_signature_verification_enabled_async(self):
        """Test decoding with signature verification enabled (should succeed with valid token)."""
        # Arrange
        token = JWTHelper.acreate_token(client=199520, school_id=1009, issuer="test-issuer", expires_in_hours=24)

        # Act
        payload = JWTHelper.adecode_token(token, verify_signature=True)

        # Assert
        assert payload is not None
        assert payload.client == 199520

    def test_decode_with_signature_verification_disabled_async(self):
        """Test decoding with signature verification disabled."""
        # Arrange
        token = JWTHelper.acreate_token(client=199520, school_id=1009, issuer="test-issuer", expires_in_hours=24)

        # Act
        payload = JWTHelper.adecode_token(token, verify_signature=False)

        # Assert
        assert payload is not None
        assert payload.client == 199520

    def test_decode_with_invalid_signature_fails_async(self):
        """Test that decoding with invalid signature fails when verification is enabled."""
        # Arrange - create a token
        token = JWTHelper.acreate_token(client=199520, school_id=1009, issuer="test-issuer", expires_in_hours=24)

        # Decode base64 to get JWT
        jwt_token = base64.b64decode(token).decode("utf-8")

        # Tamper with the token (change last characters)
        tampered_jwt = jwt_token[:-2] + "aa"

        # Re-encode to base64
        tampered_token = base64.b64encode(tampered_jwt.encode("utf-8")).decode("utf-8")

        # Act & Assert
        with pytest.raises(jwt.InvalidTokenError):
            JWTHelper.adecode_token(tampered_token, verify_signature=True)

    def test_decode_with_wrong_secret_key_fails_async(self):
        """Test that decoding with wrong secret key fails."""
        # Arrange - create a token with one secret
        token = JWTHelper.acreate_token(client=199520, school_id=1009, issuer="test-issuer", expires_in_hours=24)

        # Mock a different secret key
        with patch("envvar.EnvHelper.get_jwt_secret_key", return_value="different-secret-key"):
            # Act & Assert
            with pytest.raises(jwt.InvalidTokenError):
                JWTHelper.adecode_token(token, verify_signature=True)


class TestJWTErrorCases:
    """Tests for JWT error handling."""

    def test_decode_invalid_base64_fails_async(self):
        """Test that decoding invalid base64 fails with appropriate error."""
        # Arrange
        invalid_base64 = "this-is-not-valid-base64!!!"

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid base64-encoded token"):
            JWTHelper.adecode_token(invalid_base64, verify_signature=False)

    def test_decode_expired_token_fails_async(self):
        """Test that decoding an expired token fails."""
        # Arrange - create a token that expires immediately
        token = JWTHelper.acreate_token(client=199520, school_id=1009, issuer="test-issuer", expires_in_hours=0)

        # Wait a moment to ensure expiration
        import time

        time.sleep(1)

        # Act & Assert
        with pytest.raises(jwt.ExpiredSignatureError, match="Token has expired"):
            JWTHelper.adecode_token(token, verify_signature=False)

    def test_decode_empty_token_fails_async(self):
        """Test that decoding an empty token fails."""
        # Act & Assert
        with pytest.raises(jwt.InvalidTokenError):
            JWTHelper.adecode_token("", verify_signature=False)

    def test_decode_none_token_fails_async(self):
        """Test that decoding None fails."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid base64-encoded token"):
            JWTHelper.adecode_token(None, verify_signature=False)  # type: ignore

    def test_decode_malformed_jwt_fails_async(self):
        """Test that decoding a malformed JWT fails."""
        # Arrange - create valid base64 but invalid JWT
        malformed_jwt = "invalid.jwt.token"
        malformed_base64 = base64.b64encode(malformed_jwt.encode("utf-8")).decode("utf-8")

        # Act & Assert
        with pytest.raises(jwt.InvalidTokenError):
            JWTHelper.adecode_token(malformed_base64, verify_signature=False)


class TestJWTExtractFromHeader:
    """Tests for extracting JWT from Authorization header."""

    def test_extract_token_from_valid_header_async(self):
        """Test extracting token from valid Authorization header."""
        # Arrange
        token = "ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5"
        header = f"Bearer {token}"

        # Act
        extracted = JWTHelper.aextract_token_from_header(header)

        # Assert
        assert extracted == token

    def test_extract_token_from_header_without_bearer_fails_async(self):
        """Test that extracting from header without Bearer scheme fails."""
        # Arrange
        header = "ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5"

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid authorization header format"):
            JWTHelper.aextract_token_from_header(header)

    def test_extract_token_from_none_header_fails_async(self):
        """Test that extracting from None header fails."""
        # Act & Assert
        with pytest.raises(ValueError, match="Authorization header is missing"):
            JWTHelper.aextract_token_from_header(None)

    def test_extract_token_from_empty_header_fails_async(self):
        """Test that extracting from empty header fails."""
        # Act & Assert
        with pytest.raises(ValueError, match="Authorization header is missing"):
            JWTHelper.aextract_token_from_header("")

    def test_extract_token_with_wrong_scheme_fails_async(self):
        """Test that extracting with wrong auth scheme fails."""
        # Arrange
        header = "Basic dXNlcjpwYXNz"

        # Act & Assert
        with pytest.raises(ValueError, match="Unsupported authorization scheme"):
            JWTHelper.aextract_token_from_header(header)


class TestJWTDecodeFromHeader:
    """Tests for decode_from_header_async convenience method."""

    def test_decode_from_header_success_async(self):
        """Test successful decode from Authorization header."""
        # Arrange
        token = JWTHelper.acreate_token(client=199520, school_id=1009, issuer="test-issuer", expires_in_hours=24)
        header = f"Bearer {token}"

        # Act
        payload = JWTHelper.adecode_from_header(header, verify_signature=False)

        # Assert
        assert payload is not None
        assert payload.client == 199520
        assert payload.schoolId == 1009

    def test_decode_from_header_with_invalid_token_fails_async(self):
        """Test decode from header with invalid token fails."""
        # Arrange
        header = "Bearer invalid-token"

        # Act & Assert
        with pytest.raises(ValueError):
            JWTHelper.adecode_from_header(header, verify_signature=False)
