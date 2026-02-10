# REAL-HOLTMONT

## Cómo correr el proyecto (How to run)

### Windows (PowerShell)

**Opción 1: Automática**
Ejecuta el script `run.ps1` desde PowerShell:
```powershell
.\run.ps1
```
Esto abrirá dos ventanas de PowerShell (Backend y Frontend) y el navegador automáticamente.

**Opción 2: Manual**
Abre dos terminales de PowerShell:

Terminal 1 (Backend):
```powershell
python main.py
```
(Debe mostrar "Uvicorn running on http://0.0.0.0:8000")

Terminal 2 (Frontend):
```powershell
python -m http.server 8080
```

Luego abre tu navegador en: [http://localhost:8080](http://localhost:8080)

### Linux / Mac (Bash)

Terminal 1:
```bash
python main.py
```

Terminal 2:
```bash
python -m http.server 8080
```

### Requisitos Previos

Asegúrate de tener instaladas las dependencias:
```bash
pip install -r requirements.txt
```

### Credenciales (Modo Mock / Desarrollo)

Si no tienes `credentials.json`, puedes usar las credenciales de prueba:
- **Usuario:** `LUIS_CARLOS`
- **Contraseña:** `admin2025`
