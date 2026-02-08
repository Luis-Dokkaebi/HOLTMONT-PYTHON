from fastapi.testclient import TestClient
from main import app, gs_manager, MockSpreadsheet

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
    # In mock mode with auto-creation (needed for saves), fetching a missing sheet returns empty data
    # and message "Vacía" (because it has [[]] or []).
    # Logic in main.py: if len(values) < 2: return "Vacía"

    response = client.get("/api/data?sheet=NON_EXISTENT_SHEET")
    assert response.status_code == 200
    data = response.json()

    # Adjusted expectation for Mock mode with auto-create
    assert data["message"] == "Vacía" or "Falta hoja" in data["message"]

def test_save_ppc_workorder():
    # Test saving a Work Order (apiSavePPCData equivalent)
    payload = [{
        "cliente": "TEST CLIENT",
        "especialidad": "ELECTROMECANICA",
        "concepto": "TEST WO 001",
        "responsable": "TEST USER",
        "materiales": [
            {"cantidad": 10, "unidad": "m", "descripcion": "Cable", "costo": 100}
        ],
        "manoObra": [
            {"category": "Tecnico", "salary": 2000, "personnel": 1, "weeks": 1}
        ]
    }]

    response = client.post("/api/savePPC", json={"payload": payload, "activeUser": "PREWORK_ORDER"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["ids"]) == 1

    # Verify data was saved to mock sheets
    # 1. Main PPC Sheet
    ppc_response = client.get("/api/data?sheet=PPCV3")
    ppc_data = ppc_response.json()
    assert ppc_data["success"] is True
    saved_tasks = ppc_data["data"]
    # Look for our task (last one usually)
    found_task = next((t for t in saved_tasks if t.get("CONCEPTO") == "TEST WO 001"), None)
    assert found_task is not None
    assert found_task["CLIENTE"] == "TEST CLIENT"

    # 2. Materials Sheet
    mat_response = client.get("/api/data?sheet=DB_WO_MATERIALES")
    mat_data = mat_response.json()
    assert mat_data["success"] is True
    saved_mats = mat_data["data"]
    # Look for material with same FOLIO
    folio = found_task["FOLIO"]
    found_mat = next((m for m in saved_mats if m.get("FOLIO") == folio), None)
    assert found_mat is not None
    assert found_mat["DESCRIPCION"] == "Cable"
