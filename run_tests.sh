#!/bin/bash
source venv/bin/activate
cd /app/HOLTMONT-PYTHON-main

# Start server
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

# Wait for it to be ready
sleep 5

# Run tests
PYTHONPATH=. python -m pytest tests/test_cotizacion_preconstruccion.py -v

# Kill server
kill $SERVER_PID
