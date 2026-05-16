# Guía de Refactorización Frontend

Esta guía describe cómo integrar el nuevo backend Python/FastAPI con el frontend existente de Vue.js, reemplazando la dependencia de Google Apps Script (`google.script.run`).

## 1. Integrar el Adaptador (`api_service.js`)

El archivo `api_service.js` contiene la clase `ApiService` que se comunica con el backend Python y la clase `GoogleScriptRunAdapter` que emula la interfaz de GAS.

### Paso 1: Incluir el script en `index.html`

Abre `index.html` y agrega la referencia a `api_service.js` **antes** del bloque de script principal donde reside la lógica de Vue.

```html
<head>
  <!-- ... otros links ... -->
  <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
  <!-- ... -->

  <!-- AGREGAR ESTA LÍNEA -->
  <script src="api_service.js"></script>
</head>
```

### Paso 2: Inicializar el Mock de Google Script

Justo antes de que comience tu aplicación Vue (o al inicio del bloque `<script>` principal), inicializa el adaptador para que sobrescriba (o defina) `google.script.run`.

```html
<script>
  // ... imports o setup inicial ...

  // INICIALIZACIÓN DEL ADAPTADOR
  // Esto redirige las llamadas de google.script.run hacia tu backend Python
  if (!window.google) window.google = {};
  if (!window.google.script) window.google.script = {};

  // Reemplaza el objeto run con nuestro adaptador
  window.google.script.run = new GoogleScriptRunAdapter();

  const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;
  // ... resto del código Vue ...
</script>
```

## 2. Refactorización de `handleLogin` (doLogin)

La función `doLogin` en tu código actual usa `google.script.run.apiLogin`. Gracias al adaptador, **no necesitas cambiar la lógica interna de la función**. El adaptador interceptará la llamada.

Código actual (compatible):
```javascript
const doLogin = () => {
    if(!loginPass.value || !loginUser.value) return;
    loggingIn.value=true;

    // Esta llamada ahora usará ApiService.login() internamente
    google.script.run
        .withSuccessHandler(res => {
            loggingIn.value=false;
            if(res.success){
                isLoggedIn.value=true;
                currentUser.value=res.name;
                currentUsername.value = res.username;
                currentRole.value = res.role;

                // Asegúrate que estos métodos también estén soportados o mockeados en el Adapter
                loadConfig(res.role);
                loadCascadeTree();
            } else {
                Swal.fire('Error',res.message,'error');
            }
        })
        .withFailureHandler(handleErr)
        .apiLogin(loginUser.value, loginPass.value);
};
```

## 3. Ejecución

1.  Asegúrate de que el backend esté corriendo:
    ```bash
    python3 main.py
    ```
    Estará escuchando en `http://localhost:8000`.

2.  Abre `index.html` en tu navegador.
    *   Si usas un servidor local (ej. Live Server), asegúrate de que el puerto del `API_BASE_URL` en `api_service.js` coincida o que CORS esté configurado correctamente en `main.py` (actualmente permite `*`).

3.  Intenta iniciar sesión.
    *   Usuarios predeterminados (Mock): `LUIS_CARLOS` / `admin2025`.
