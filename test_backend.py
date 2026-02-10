from fastapi.testclient import TestClient
from api.main import app, gs_manager, MockSpreadsheet

client = TestClient(app)

# Force Mock mode for testing
gs_manager.is_mock = True
gs_manager.ss = MockSpreadsheet()

def test_login_success():
    # Test valid credentials (mocked)
    response = client.post("/api/login", json={"username": "LUIS_CARLOS", "password": "admin2025"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["username"] == "LUIS_CARLOS"
    assert data["role"] == "ADMIN"

def test_login_failure():
    # Test invalid credentials
    response = client.post("/api/login", json={"username": "LUIS_CARLOS", "password": "wrongpassword"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False

def test_fetch_data_mock():
    # Test fetching mock data
    response = client.get("/api/data?sheet=ANTONIA_VENTAS")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "headers" in data
    assert "data" in data
    # Check mock data content
    assert len(data["data"]) >= 1
    first_row = data["data"][0]
    assert first_row["CLIENTE"] == "CLIENTE A"
    assert first_row["ESTATUS"] == "PENDIENTE"

def test_fetch_data_missing():
    # Test fetching non-existent sheet
    response = client.get("/api/data?sheet=NON_EXISTENT_SHEET")
    assert response.status_code == 200
    data = response.json()
    # In mock mode, we expect "Falta hoja" or similar message
    # Logic in main.py: if not values: return { ... message: "Falta hoja..." }
    assert "Falta hoja" in data.get("message", "")

def test_home_route():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "status": "online",
        "message": "API de Holtmont-Python funcionando correctamente",
        "version": "1.0.0"
    }
