# REAL-HOLTMONT

## Configuration

This project requires environment variables to be set in a `.env` file in the root directory.

### Required Variables

- `GROQ_API_KEY`: API Key for Groq (AI transcription and analysis).

Example `.env` file:
```
GROQ_API_KEY=your_api_key_here
```

## Running Tests

To run tests, install dependencies and run:
```bash
pip install -r requirements.txt
pip install pytest httpx
python -m pytest
```
