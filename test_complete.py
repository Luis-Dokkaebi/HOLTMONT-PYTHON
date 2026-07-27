import sys
import os
sys.path.insert(0, os.path.abspath("."))
from api.services.tracker_rules import apply_batch_update

values = [
    ["FOLIO", "CONCEPTO", "AVANCE", "ESTATUS"],
    ["F-1", "Concepto 1", "100.0%", "EN PROCESO"],
    ["F-2", "Concepto 2", "50%", "EN PROCESO"]
]
tasks = [
    {"FOLIO": "F-1", "CONCEPTO": "Concepto 1", "AVANCE": "100.0%", "ESTATUS": "EN PROCESO"},
]
res = apply_batch_update(values, tasks, "TEST_SHEET")
print("moved:", res.moved)
