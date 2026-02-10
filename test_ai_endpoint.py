from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from api.main import app, gs_manager, MockSpreadsheet
import os

client = TestClient(app)

# Force Mock mode for testing
gs_manager.is_mock = True
gs_manager.ss = MockSpreadsheet()

def test_transcribe_and_analyze_success():
    mock_transcription = "This is a test transcription."
    mock_extraction = {
        "folio": "1234",
        "descripcion_generica": "Test Description"
    }

    with patch("api.main.transcribir_audio") as mock_transcribe:
        with patch("api.main.extraer_informacion") as mock_extract:
            mock_transcribe.return_value = mock_transcription
            mock_extract.return_value = {"extraction": mock_extraction, "error": ""}

            files = {'file': ('audio.wav', b'dummy content', 'audio/wav')}
            # Pass a dummy key to bypass the environment variable check if needed,
            # though the endpoint checks form data or env var.
            data = {'apiKey': 'dummy_key'}

            response = client.post("/api/transcribe_and_analyze", files=files, data=data)

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["success"] is True
            assert json_response["transcription"] == mock_transcription
            assert json_response["data"] == mock_extraction

def test_transcribe_and_analyze_transcription_error():
    with patch("api.main.transcribir_audio") as mock_transcribe:
        mock_transcribe.return_value = "Error: Transcription failed"

        files = {'file': ('audio.wav', b'dummy content', 'audio/wav')}
        data = {'apiKey': 'dummy_key'}

        response = client.post("/api/transcribe_and_analyze", files=files, data=data)

        assert response.status_code == 200
        json_response = response.json()
        assert json_response["success"] is False
        assert "Error" in json_response["message"]

def test_transcribe_and_analyze_extraction_error():
    mock_transcription = "This is a test transcription."
    with patch("api.main.transcribir_audio") as mock_transcribe:
        with patch("api.main.extraer_informacion") as mock_extract:
            mock_transcribe.return_value = mock_transcription
            mock_extract.return_value = {"extraction": None, "error": "Extraction failed"}

            files = {'file': ('audio.wav', b'dummy content', 'audio/wav')}
            data = {'apiKey': 'dummy_key'}

            response = client.post("/api/transcribe_and_analyze", files=files, data=data)

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["success"] is False
            assert json_response["message"] == "Extraction failed"

def test_transcribe_and_analyze_missing_key():
    # Ensure no env var
    with patch.dict(os.environ, {}, clear=True):
        files = {'file': ('audio.wav', b'dummy content', 'audio/wav')}
        response = client.post("/api/transcribe_and_analyze", files=files)
        assert response.status_code == 400
        assert "Falta GROQ_API_KEY" in response.json()["detail"]
