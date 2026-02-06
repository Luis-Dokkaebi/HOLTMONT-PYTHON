# REAL-HOLTMONT

## Migración a Python/FastAPI

Este proyecto ha sido migrado de Google Apps Script a un backend Python con FastAPI.

### Requisitos

*   Python 3.8+
*   Pip

### Instalación

1.  Clona el repositorio.
2.  Instala las dependencias:
    ```bash
    pip install -r requirements.txt
    ```

### Ejecución del Backend

El backend maneja la lógica de negocio y la conexión con Google Sheets (o Mocks si no hay credenciales).

1.  Inicia el servidor:
    ```bash
    python main.py
    ```
    O usando uvicorn directamente:
    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

    El servidor iniciará en `http://localhost:8000`.

### Ejecución del Frontend

El frontend sigue siendo HTML/Vue.js estático, pero ahora se comunica con el backend local.

1.  Opción A: Abrir directamente `index.html` en el navegador.
2.  Opción B (Recomendada): Usar un servidor HTTP simple para evitar bloqueos de CORS/archivos locales.
    ```bash
    python -m http.server 8080
    ```
    Luego abre `http://localhost:8080` en tu navegador.

### Credenciales

*   **Producción**: Coloca tu archivo `credentials.json` de Google Service Account en la raíz del proyecto.
*   **Desarrollo/Test**: Si no existe `credentials.json`, el sistema usará datos simulados (Mock) automáticamente.
    *   Usuario de prueba: `LUIS_CARLOS`
    *   Contraseña: `admin2025`

### Estructura

*   `main.py`: Código del servidor FastAPI.
*   `api_service.js`: Adaptador JavaScript que conecta el frontend con el backend.
*   `test_backend.py`: Pruebas automatizadas del backend.
