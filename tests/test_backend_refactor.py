import sys
import os
import pytest
from datetime import datetime

# Ensure api module can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.main import api_save_ppc_data, SavePPCRequest, gs_manager

def test_save_ppc_logic():
    # Ensure we are in Mock Mode
    if not gs_manager.is_mock:
        pytest.skip("Skipping test because we are not in Mock Mode (credentials found)")

    # Prepare Mock Data
    payload = [{
        "cliente": "TEST CLIENT",
        "especialidad": "TEST DEPT",
        "concepto": "Test Concept",
        "responsable": "TEST USER",
        "prioridad": "Alta",
        "fechaRespuesta": "01/01/2025",
        "materiales": [
            {"quantity": "10", "unit": "pza", "description": "Test Material", "cost": "100", "total": "1000"}
        ],
        "manoObra": [
            {"category": "Test Labor", "salary": "1000", "personnel": "1", "weeks": "1", "total": "1000"}
        ]
    }]

    request = SavePPCRequest(payload=payload, activeUser="TEST_USER")

    # call the function
    response = api_save_ppc_data(request)

    assert response["success"] is True
    assert "ids" in response
    assert len(response["ids"]) == 1

    # Verify data in Mock Sheets
    # Check PPCV3
    ppc_sheet = gs_manager.get_sheet_values("PPCV3")
    assert ppc_sheet is not None
    # Find the row (last one)
    last_row = ppc_sheet[-1]
    # Check concept
    assert "Test Concept" in last_row

    # Check Materials Sheet
    mat_sheet = gs_manager.get_sheet_values("DB_WO_MATERIALES")
    assert mat_sheet is not None
    last_mat = mat_sheet[-1]
    assert "Test Material" in last_mat
    assert response["ids"][0] in last_mat # Folio should match

if __name__ == "__main__":
    pytest.main([__file__])
