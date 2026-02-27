"""Tests for REST API authentication and health endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import _verify_api_key, api


# ---------------------------------------------------------------------------
# _verify_api_key helper
# ---------------------------------------------------------------------------


class TestVerifyApiKey:
    """Validate the key-checking helper in isolation."""

    def test_no_configured_key_allows_any_request(self) -> None:
        """Auth is disabled when API_SECRET_KEY is empty."""
        with patch("src.api.settings") as mock_settings:
            mock_settings.api_secret_key = ""
            # Should not raise
            _verify_api_key(None)
            _verify_api_key("random-junk")

    def test_configured_key_accepts_correct_header(self) -> None:
        with patch("src.api.settings") as mock_settings:
            mock_settings.api_secret_key = "supersecret"
            # Should not raise
            _verify_api_key("supersecret")

    def test_configured_key_rejects_wrong_header(self) -> None:
        with patch("src.api.settings") as mock_settings:
            mock_settings.api_secret_key = "supersecret"
            with pytest.raises(HTTPException) as exc_info:
                _verify_api_key("wrongkey")
        assert exc_info.value.status_code == 401

    def test_configured_key_rejects_missing_header(self) -> None:
        with patch("src.api.settings") as mock_settings:
            mock_settings.api_secret_key = "supersecret"
            with pytest.raises(HTTPException) as exc_info:
                _verify_api_key(None)
        assert exc_info.value.status_code == 401

    def test_configured_key_rejects_empty_string_header(self) -> None:
        with patch("src.api.settings") as mock_settings:
            mock_settings.api_secret_key = "supersecret"
            with pytest.raises(HTTPException):
                _verify_api_key("")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_ok(self) -> None:
        client = TestClient(api)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
