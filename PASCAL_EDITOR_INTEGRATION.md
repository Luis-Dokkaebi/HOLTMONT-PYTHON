# Guía de Arquitectura e Integración Completa: Pascal Editor y REAL-HOLTMONT

Este documento constituye la guía definitiva, detallada y paso a paso para lograr la integración entre nuestra plataforma de cotizaciones (REAL-HOLTMONT, construida en Vue.js y FastAPI) y el **Pascal Editor** (una potente herramienta open-source de diseño arquitectónico 3D en la nube construida en React, Next.js, React Three Fiber y WebGPU).

El objetivo principal de esta integración es proporcionar a los cotizadores y clientes una interfaz visual, alojada en una "vista separada", que permita realizar "Pre-Diseños". El gran reto resuelto en este documento es la **comunicación segura y asíncrona (extracción de datos)** entre el iframe que contiene el Pascal Editor y nuestra aplicación principal, lo cual permitirá almacenar el JSON arquitectónico directamente en la base de datos de Work Orders de Google Sheets.

---

## ÍNDICE DE CONTENIDOS

1. [Consideraciones Previas y Arquitectónicas](#1-consideraciones-previas-y-arquitectónicas)
2. [Fase 1: Preparación, Fork y Despliegue del Pascal Editor](#2-fase-1-preparación-fork-y-despliegue-del-pascal-editor)
3. [Fase 2: Modificación del Código Fuente del Pascal Editor (React/Zustand)](#3-fase-2-modificación-del-código-fuente-del-pascal-editor-reactzustand)
4. [Fase 3: Modificación del Frontend Principal de REAL-HOLTMONT (Vue.js / `index.html`)](#4-fase-3-modificación-del-frontend-principal-de-real-holtmont-vuejs--indexhtml)
5. [Fase 4: Adaptación del Backend FastAPI para Recibir Datos de Diseño 3D](#5-fase-4-adaptación-del-backend-fastapi-para-recibir-datos-de-diseño-3d)
6. [Fase 5: Actualización del Repositorio de Google Sheets](#6-fase-5-actualización-del-repositorio-de-google-sheets)
7. [Fase 6: Diagramas de Flujo y Casos de Uso Extendidos](#7-fase-6-diagramas-de-flujo-y-casos-de-uso-extendidos)
8. [Fase 7: Consideraciones de Seguridad (CORS / postMessage)](#8-fase-7-consideraciones-de-seguridad-cors--postmessage)
9. [Fase 8: Mantenimiento y Actualizaciones del Fork](#9-fase-8-mantenimiento-y-actualizaciones-del-fork)
10. [Conclusiones y Siguientes Pasos](#10-conclusiones-y-siguientes-pasos)
11. [Anexos: Solución de Problemas Comunes (Troubleshooting)](#11-anexos-solución-de-problemas-comunes-troubleshooting)
12. [Glosario de Términos](#12-glosario-de-términos)

---

## 1. CONSIDERACIONES PREVIAS Y ARQUITECTÓNICAS

La plataforma de Pascal Editor está basada en Next.js. Funciona de manera autónoma como un SPA (Single Page Application). Nuestra plataforma, REAL-HOLTMONT, está diseñada en un monolito front-end con Vue 3 sin build-step (incrustado directamente en `index.html`) respaldado por un backend en Python (FastAPI).

### ¿Por qué la estrategia de iFrame + Fork?

Las restricciones de seguridad "Same-Origin Policy" (SOP) dictaminadas por los navegadores modernos impiden que una página web primaria (nuestro Vue.js) extraiga el DOM, las variables o el almacenamiento interno de un iFrame si este proviene de un dominio diferente.

**Mala práctica:** Intentar hacer un `iframe.contentWindow.document.getElementById(...)`. Esto lanzará un error de CORS inmediatamente.
**Solución adoptada:** Un esquema de **Mensajería Bidireccional Segura** usando el API nativa de la web `window.postMessage`. Para que el iFrame pueda enviar estos mensajes, es OBLIGATORIO que tengamos control sobre su código fuente. Por eso, alojar el repositorio de Pascal Editor bajo nuestra propia cuenta y modificarlo es el único camino viable.

### Impacto en la Arquitectura de Datos

El diseño 3D generado por Pascal Editor se almacena en un objeto JSON profundo (con estructura de nodos, mallas y configuraciones).
Este JSON puede llegar a tener varios megabytes de tamaño dependiendo de la complejidad del edificio.
Debemos asegurarnos de que la base de datos de destino (Google Sheets u otro medio) tenga la capacidad de almacenar cadenas de texto muy extensas o, como alternativa, implementar un mecanismo de almacenamiento en blobs y guardar solo la referencia.

---

## 2. FASE 1: PREPARACIÓN, FORK Y DESPLIEGUE DEL PASCAL EDITOR

Para comenzar la integración real, lo primero es aislar el código fuente de Pascal Editor para que sea de nuestro dominio exclusivo.

### 2.1 Bifurcación (Fork) del Repositorio Original
1. Navega al repositorio open source oficial de Pascal Editor.
2. Haz clic en el botón superior derecho "Fork" y selecciona la organización o cuenta personal de la empresa de Holtmont.
3. Esto clonará todo el historial y ramas en nuestra propia cuenta de GitHub, lo que nos da independencia total para modificar el código sin depender de Pull Requests al autor original.
4. Clona el nuevo fork a tu máquina local usando la terminal:
   ```bash
   # Cambiar TU_USUARIO por el usuario de la cuenta que hizo el fork
   git clone https://github.com/TU_USUARIO/pascal-editor-holtmont.git
   cd pascal-editor-holtmont

   # Pascal Editor usa un gestor de paquetes (puede ser pnpm, yarn o npm, revisa su documentación)
   # Asumiendo npm:
   npm install
   ```

### 2.2 Despliegue en Infraestructura Independiente
Dado que Pascal Editor requiere un proceso de "build" en Node.js, es recomendable alojarlo de forma independiente a la API de Python.

- **Vercel:** Vercel es la plataforma ideal para Next.js.
  - Crea una cuenta y un nuevo proyecto.
  - Vincula tu repositorio bifurcado (`pascal-editor-holtmont`).
  - Vercel detectará que es Next.js y aplicará automáticamente `npm run build` y la ruta de salida.
- **Alternativas:** Render o Netlify también funcionarán.
- **Obtención de URL:** Al finalizar el despliegue obtendrás una URL pública. Ejemplo ficticio: `https://pascal-holtmont.vercel.app`. Esta URL es crucial y se utilizará más adelante en nuestro código Vue.

### 2.3 Variables de Entorno del Editor
Si el editor original de Pascal Editor requiriese alguna llave para librerías o APIs internas (como mapbox, autenticación temporal, etc.), asegúrate de configurar esas variables de entorno en el panel de Vercel/Render.

---

## 3. FASE 2: MODIFICACIÓN DEL CÓDIGO FUENTE DEL PASCAL EDITOR (React/Zustand)

El corazón de Pascal Editor utiliza `Zustand` como manejador de estado global. Allí es donde reside la "fuente de la verdad" del edificio 3D (muros, pisos, muebles, etc.). Necesitamos interceptar el evento de "Guardado" (o crear un botón de "Exportar a Holtmont") para inyectar nuestra comunicación.

### 3.1 Creando el botón de comunicación
En el repositorio del Pascal Editor (nuestro fork), busca el componente de navegación superior. Suele estar en rutas como `src/components/ui/Toolbar.tsx`, `Header.tsx` o `src/app/layout.tsx`.

Vamos a inyectar un nuevo botón diseñado específicamente para nuestra integración.

**Crear el archivo `src/components/ui/HoltmontExportButton.tsx`:**

```tsx
import React, { useCallback, useState } from 'react';
import { useStore } from '../../store/useStore'; // IMPORTANTE: Ajustar ruta al store de Zustand real

export const HoltmontExportButton: React.FC = () => {
  const [isExporting, setIsExporting] = useState(false);

  // Extraemos la función o el estado completo de la arquitectura
  // Zustand normalmente permite obtener todo el estado usando getState() o un selector
  const getFullProjectState = useStore((state) => state.exportProjectJSON);

  const handleExport = useCallback(() => {
    setIsExporting(true);

    try {
      // 1. Obtener la serialización JSON del edificio actual
      // Si la función exportProjectJSON no existe, puede que necesites extraer estado por estado:
      // const projectData = { walls: state.walls, floors: state.floors, ... };
      const projectData = getFullProjectState();

      // 2. Preparar el payload de comunicación segura
      const payload = {
        type: 'HOLTMONT_3D_EXPORT',
        data: projectData,
        version: '1.0',
        timestamp: new Date().toISOString()
      };

      // 3. Enviar mensaje asíncrono al componente "Padre" (nuestro Vue.js en index.html)
      // Usamos "*" temporalmente para dev, pero en PROD debe ser "https://nuestro-dominio-holtmont.com"
      // window.parent hace referencia a la ventana que contiene el iFrame
      window.parent.postMessage(payload, '*');

      // Feedback visual
      alert('Diseño exportado correctamente a REAL-HOLTMONT');
    } catch (error) {
      console.error('Error crítico exportando diseño 3D a la app padre', error);
      alert('Hubo un error al exportar el diseño. Verifica la consola para más detalles.');
    } finally {
      setIsExporting(false);
    }
  }, [getFullProjectState]);

  return (
    <button
      onClick={handleExport}
      disabled={isExporting}
      style={{
        backgroundColor: '#0056b3', // Color azul corporativo de Holtmont
        color: 'white',
        border: 'none',
        padding: '8px 16px',
        borderRadius: '4px',
        fontWeight: 'bold',
        cursor: isExporting ? 'not-allowed' : 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
      }}
    >
      <span className="icon">💾</span>
      {isExporting ? 'Exportando...' : 'Guardar en Holtmont'}
    </button>
  );
};
```

Luego, asegúrate de importar y renderizar este `HoltmontExportButton` dentro de la interfaz principal del editor (Toolbar).

### 3.2 Escucha de Inicialización y Carga (Importación a Pascal Editor)
Es fundamental no solo guardar, sino poder cargar un diseño previamente guardado cuando el usuario decida editarlo.

Añadir este código en el componente principal de la app de Next.js (ej. `src/pages/index.tsx`, `src/app/page.tsx` o un layout global persistente):

```tsx
import { useEffect } from 'react';
import { useStore } from '../store/useStore'; // Ajustar ruta

export default function AppLayout({ children }) {
  useEffect(() => {
    // Definimos el listener
    const handleIncomingMessage = (event: MessageEvent) => {
      // Validar origen por seguridad (Descomentar en producción)
      // const allowedOrigins = ["https://tu-sitio-vue.com", "http://localhost:8000"];
      // if (!allowedOrigins.includes(event.origin)) return;

      if (event.data && event.data.type === 'HOLTMONT_3D_IMPORT') {
        console.log('Recibiendo payload de diseño desde base de datos Holtmont', event.data.projectData);

        try {
          // Asumiendo que el store tiene una función loadProjectJSON
          // useStore.getState().loadProjectJSON(event.data.projectData);

          // O si es usando acciones expuestas:
          const actions = useStore.getState().actions;
          if (actions && actions.loadProject) {
            actions.loadProject(event.data.projectData);
          } else {
             console.warn("La función de carga no fue encontrada en el store de Zustand");
          }
        } catch (err) {
           console.error("Error al inyectar diseño en el canvas:", err);
        }
      }
    };

    // Suscribir al evento 'message' global
    window.addEventListener('message', handleIncomingMessage);

    // Cleanup function: desuscribirse cuando el componente se desmonte
    return () => window.removeEventListener('message', handleIncomingMessage);
  }, []);

  return <>{children}</>;
}
```

---

## 4. FASE 3: MODIFICACIÓN DEL FRONTEND PRINCIPAL DE REAL-HOLTMONT (Vue.js / `index.html`)

Aquí es donde nuestro equipo integrará la vista del usuario final. Modificaremos nuestro `index.html` actual.

### 4.1 Creación de la Vista Separada en Vue.js

En el archivo `index.html`, localizar la navegación y el sistema de vistas. Actualmente tenemos estados como `currentView = 'WORKORDER_FORM'`. Necesitamos crear uno nuevo: `currentView = 'PASCAL_DESIGNER'`.

En el menú superior o barra lateral de la aplicación, añade el botón de navegación:

```html
<!-- En la barra de navegación lateral o superior -->
<li class="nav-item">
  <!-- Utilizamos prevent para evitar que recargue la página -->
  <a class="nav-link" href="#" @click.prevent="currentView = 'PASCAL_DESIGNER'">
    <i class="fas fa-cube"></i> Pre-Diseños 3D
  </a>
</li>
```

### 4.2 Inyección del contenedor HTML del iFrame

En la sección donde se renderizan las vistas basadas en `v-if` (probablemente debajo del bloque `<div v-if="currentView === 'WORKORDER_FORM'">`), añade el siguiente bloque masivo de código estructural:

```html
<!-- VISTA DEL EDITOR PASCAL 3D -->
<div v-if="currentView === 'PASCAL_DESIGNER'" class="pascal-designer-view h-100 p-3">

  <!-- Header de la vista -->
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h2><i class="fas fa-pencil-ruler text-primary me-2"></i> Pre-Diseños 3D Arquitectónicos</h2>
    <div>
      <button class="btn btn-outline-secondary me-3 shadow-sm" @click="currentView = 'WORKORDER_FORM'">
        <i class="fas fa-arrow-left"></i> Volver a Work Order
      </button>

      <!-- Indicadores visuales de estado del diseño -->
      <span class="badge bg-success p-2 text-white shadow-sm" v-if="design3DStatus === 'SAVED'">
        <i class="fas fa-check-circle me-1"></i> Diseño Anexado a Work Order
      </span>
      <span class="badge bg-warning p-2 text-dark shadow-sm" v-else-if="design3DStatus === 'PENDING'">
        <i class="fas fa-exclamation-triangle me-1"></i> Diseño no anexado
      </span>
      <span class="badge bg-danger p-2 text-white shadow-sm" v-else-if="design3DStatus === 'ERROR'">
        <i class="fas fa-times-circle me-1"></i> Error al recuperar diseño
      </span>
    </div>
  </div>

  <!-- Contenedor Principal del IFrame -->
  <div class="card shadow border-0 h-100" style="border-radius: 12px; overflow: hidden;">
    <div class="card-body p-0 m-0" style="height: 85vh; min-height: 700px; position: relative;">

      <!-- Overlay de Pantalla de carga mientras levanta el iFrame -->
      <div v-if="!iframeLoaded" class="position-absolute top-0 start-0 w-100 h-100 d-flex flex-column justify-content-center align-items-center bg-light z-index-2">
        <div class="spinner-border text-primary mb-3" style="width: 3rem; height: 3rem;" role="status">
          <span class="visually-hidden">Cargando motor 3D...</span>
        </div>
        <h4 class="text-secondary font-weight-bold">Inicializando Pascal Engine 3D...</h4>
        <p class="text-muted small">Esto puede tardar unos segundos la primera vez.</p>
      </div>

      <!-- El Iframe en sí. Apuntando a tu fork alojado y referenciado reactivamente -->
      <iframe
        id="pascal-editor-iframe"
        :src="pascalEditorUrl"
        style="width: 100%; height: 100%; border: none; display: block;"
        @load="onIframeLoaded"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; webgl"
        allowfullscreen>
      </iframe>
    </div>
  </div>
</div>
```

### 4.3 Lógica del Controlador de Vue 3 (`setup()`)

Dentro del `<script>` del `index.html`, en la función `setup()` de Vue. Debes añadir una serie de nuevas variables reactivas y funciones.

```javascript
// ==========================================
// NUEVAS REFERENCIAS REACTIVAS PARA PASCAL 3D
// ==========================================

// CAMBIAR POR TU URL REAL DE VERCEL o RENDER
const pascalEditorUrl = Vue.ref('https://pascal-holtmont.vercel.app');
const iframeLoaded = Vue.ref(false);
const design3DStatus = Vue.ref('PENDING'); // 'PENDING', 'SAVED', 'ERROR'
const saved3DProjectData = Vue.ref(null); // Aquí vivirá el JSON masivo

// ==========================================
// FUNCIÓN PARA MANEJAR LA CARGA VISUAL DEL IFRAME
// ==========================================
const onIframeLoaded = () => {
  iframeLoaded.value = true;
  console.log("Iframe de Pascal Editor ha sido cargado en el DOM.");

  // Opcional: Pequeño retraso para asegurar que la app de React dentro terminó de arrancar
  setTimeout(() => {
      // Si tenemos un diseño guardado previamente (porque estamos editando una WO existente)
      // y queremos precargarlo, enviamos mensaje aquí.
      if (saved3DProjectData.value) {
        console.log("Enviando diseño existente al iFrame para su renderización...");
        const iframe = document.getElementById('pascal-editor-iframe');
        if (iframe && iframe.contentWindow) {
          iframe.contentWindow.postMessage({
            type: 'HOLTMONT_3D_IMPORT',
            projectData: saved3DProjectData.value
          }, '*');
        }
      }
  }, 1500); // 1.5 segundos de gracia
};

// ==========================================
// LISTENER PRINCIPAL DE SEGURIDAD (POSTMESSAGE)
// ==========================================
Vue.onMounted(() => {
  window.addEventListener('message', (event) => {
    // 1. Verificación de Seguridad. IMPORTANTE EN PRODUCCIÓN
    // La origin del evento debe coincidir con el dominio del Pascal Editor hospedado
    // const expectedOrigin = new URL(pascalEditorUrl.value).origin;
    // if (event.origin !== expectedOrigin) {
    //   console.warn(`Mensaje bloqueado: Origen ${event.origin} no autorizado.`);
    //   return;
    // }

    const data = event.data;

    // 2. Procesar el evento esperado de exportación
    if (data && data.type === 'HOLTMONT_3D_EXPORT') {
      console.log('Recibiendo datos de arquitectura de Pascal Editor (PostMessage)', data);

      // Guardamos la geometría profunda en la memoria local de Vue
      saved3DProjectData.value = data.data;

      // Actualizamos el estado visual de la UI
      design3DStatus.value = 'SAVED';

      // Notificación amigable al usuario (asumiendo uso de SweetAlert)
      if (window.Swal) {
          Swal.fire({
            icon: 'success',
            title: 'Diseño Capturado con Éxito',
            text: 'El diseño 3D se ha adjuntado a la memoria. Se guardará permanentemente cuando presiones Guardar Work Order.',
            timer: 3500,
            showConfirmButton: false,
            position: 'top-end',
            toast: true
          });
      } else {
          alert('Diseño Capturado con éxito y listo para ser guardado.');
      }

      // Opcional: Redirigir automáticamente de vuelta al formulario tras guardar
      // currentView.value = 'WORKORDER_FORM';
    }
  });
});

// ==========================================
// MODIFICAR LA FUNCIÓN DE GUARDADO EXISTENTE
// ==========================================
// Busca la función `saveWorkOrder` y modifica el empaquetado (payload)

/* Ejemplo simplificado de lo que debes encontrar y modificar:
const saveWorkOrder = async () => {
  ... lógica previa de validación ...

  const payload = {
    // ... campos existentes (cliente, folio, materiales, etc) ...
    folio: workorderData.folio,

    // NUEVA INYECCIÓN DE DATOS 3D
    // Lo convertimos a string porque es mucho más fácil transportarlo y guardarlo
    // en una sola celda de Google Sheets.
    arquitectura_3d_json: saved3DProjectData.value ? JSON.stringify(saved3DProjectData.value) : ""
  };

  ... continuar con apiService.submitWorkOrder(payload) ...
}
*/

// ==========================================
// NO OLVIDAR EXPORTAR LAS NUEVAS VARIABLES
// ==========================================
// Busca el final de setup() que tiene el bloque "return { ... }"
return {
  // ... variables previas ...
  pascalEditorUrl,
  iframeLoaded,
  onIframeLoaded,
  design3DStatus,
  saved3DProjectData,
  // ...
};
```

---

## 5. FASE 4: ADAPTACIÓN DEL BACKEND FASTAPI PARA RECIBIR DATOS DE DISEÑO 3D

Para que la información masiva vieja desde la app Vue hasta Google Sheets o tu base de datos, debemos decirle a FastAPI que acepte este nuevo atributo.

### 5.1 Esquema Pydantic (`api/services/work_order.py` o donde estén los schemas)

Localiza las declaraciones de Pydantic que validan el cuerpo de la petición POST. Suelen estar definidas como clases que heredan de `BaseModel`.

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class WorkOrderCreate(BaseModel):
    # Campos existentes (ejemplo):
    folio: str
    cliente: str
    descripcion: str

    # NUEVO CAMPO AGREGADO:
    # Usamos string asumiendo que el JSON fue "stringificado" en Vue.
    # Puede ser muy largo, pydantic lo aceptará.
    arquitectura_3d_json: Optional[str] = Field(default="", description="JSON serializado del proyecto de Pascal Editor 3D")

    # Alternativa: Si decidiste no usar JSON.stringify en Vue,
    # FastAPI lo puede recibir como un diccionario anidado puro:
    # arquitectura_3d_data: Optional[Dict[str, Any]] = None
```

---

## 6. FASE 5: ACTUALIZACIÓN DEL REPOSITORIO DE GOOGLE SHEETS

El destino final de los datos es la hoja de cálculo de Google Sheets. Aquí guardaremos el string de configuración de Pascal Editor para recuperarlo en un futuro si es necesario.

### 6.1 Backend (`api/services/sheets.py`)

Localiza la función donde se formatea la fila (`row_data`) que se inyectará (append) a gspread.

```python
def append_work_order_to_sheet(sheet_service, wo_data: dict):
    # Extraemos la data 3D del diccionario enviado
    arq_3d_string = wo_data.get('arquitectura_3d_json', '')

    # ADVERTENCIA DE TAMAÑO:
    # Google Sheets tiene un límite de 50,000 caracteres por celda individual.
    # Si los diseños de Pascal Editor superan este límite con regularidad,
    # la mejor arquitectura a futuro será:
    # 1. Guardar arq_3d_string en un archivo JSON en AWS S3, Google Cloud Storage, o en el disco del servidor.
    # 2. Guardar únicamente la URL del archivo en Google Sheets.

    # Para la fase de prueba, asumiremos que cabe dentro de los 50K chars:

    row_data = [
        wo_data.get('folio', ''),
        wo_data.get('cliente', ''),
        # ... demás columnas existentes mapeadas en el orden correcto ...

        # NUEVA COLUMNA INYECTADA (Añadir al final del array)
        arq_3d_string
    ]

    # Insertar en la hoja principal
    sheet_service.append_row('BASE GENERAL', row_data)
```

**Nota para Operaciones:** Deberás abrir tu Google Sheets "BASE GENERAL" y agregar una nueva cabecera en la última columna vacía (por ejemplo, columna Z) y nombrarla "ARQUITECTURA_3D_JSON" para que la tabla sea consistente.

### 6.2 Modificaciones en Recuperación de Work Orders (Opcional pero Recomendado)
Si el sistema actual tiene una función para abrir una Work Order ya existente, deberás asegurarte de que `api/services/sheets.py` lea esa columna, y la envíe en la respuesta GET hacia Vue, de forma que Vue asigne ese valor a `saved3DProjectData.value` y el iFrame pueda redibujar la escena.

---

## 7. FASE 6: DIAGRAMAS DE FLUJO Y CASOS DE USO EXTENDIDOS

Para evitar ambigüedades técnicas, repasemos el flujo de ciclo de vida completo de un diseño:

### Flujo de Creación:
1. **Acceso:** Usuario abre REAL-HOLTMONT en Vue.js y navega a la vista separada "Pre-Diseños 3D".
2. **Arranque:** Vue.js invoca al componente iframe. El navegador solicita la página de Next.js desde Vercel.
3. **Diseño:** El usuario interactúa libremente con WebGPU, dibujando muros, añadiendo niveles y amoblando la habitación sin afectar el rendimiento de Vue.js.
4. **Trigger de Exportación:** El usuario da clic en el botón customizado "Guardar en Holtmont".
5. **Transmisión:** El clon de Pascal Editor serializa el mapa 3D a JSON y emite un evento al padre: `window.parent.postMessage({ type: 'HOLTMONT_3D_EXPORT', data: {...} })`.
6. **Intercepción:** Vue.js captura el evento a través del `window.addEventListener('message')`.
7. **Retención Local:** Vue.js guarda el JSON masivo en la variable reactiva `saved3DProjectData`. El estado visual de la UI cambia a 'Diseño Anexado'.
8. **Finalización de WO:** El usuario regresa a la vista de "Pre Work Order", completa la cotización textual, y da clic en el botón principal de "Guardar".
9. **Empaquetado y Red:** Vue.js agrupa todos los datos de formulario más el `arquitectura_3d_json` en una sola petición POST y la envía por HTTP.
10. **Backend FastAPI:** Valida los datos usando Pydantic y lo procesa hacia la capa de servicios de Sheets.
11. **Persistencia Final:** FastAPI inserta una nueva fila en Google Sheets. La última celda contendrá el JSON comprimido del modelo 3D.

---

## 8. FASE 7: CONSIDERACIONES DE SEGURIDAD (CORS / postMessage)

### Vulnerabilidades de Origen Cruzado (XSS)

El método `postMessage` es increíblemente útil, pero también es el principal vector de vulnerabilidades si no se aplica con restricciones estrictas (XSS).

**REGLA DE ORO 1: Emitir con Restricciones (Pascal Editor -> Vue)**
Cuando envíes los datos desde el iFrame de Pascal, **nunca** uses el asterisco en un entorno productivo.
```javascript
// PELIGROSO EN PRODUCCIÓN
window.parent.postMessage(payload, '*');

// CORRECTO EN PRODUCCIÓN
// Asegura que el JSON solo sea leído si el dominio padre es el oficial de Holtmont.
window.parent.postMessage(payload, 'https://real-holtmont-app.com');
```

**REGLA DE ORO 2: Escuchar con Verificación (Vue -> Pascal Editor)**
En el frontend principal (`index.html`), **nunca** aceptes mensajes sin validar de dónde vienen. Un script malicioso inyectado podría falsificar el evento.
```javascript
window.addEventListener('message', (event) => {
    // Si la solicitud de mensaje no proviene de tu clon de Vercel, abortar de inmediato.
    const expectedOrigin = 'https://pascal-holtmont.vercel.app';

    if (event.origin !== expectedOrigin) {
        console.error('ALERTA DE SEGURIDAD: Mensaje ignorado de origen no confiable:', event.origin);
        return;
    }

    // Ahora es seguro procesar event.data
});
```

---

## 9. FASE 8: MANTENIMIENTO Y ACTUALIZACIONES DEL FORK

Dado que hemos optado por bifurcar (Fork) el código, nos desligamos momentáneamente del tronco principal. Sin embargo, el equipo de código abierto de Pascal Editor continuará mejorando el sistema (optimizaciones gráficas, nuevos módulos de muebles, corrección de bugs).

Para absorber esas mejoras sin perder nuestro botón "Exportar a Holtmont":

1. **Configura el Remote Original en tu máquina local:**
   ```bash
   git remote add upstream https://github.com/pascalorg/editor
   ```
2. **Comprobar si hay actualizaciones:**
   ```bash
   git fetch upstream
   ```
3. **Fusionar las mejoras del tronco oficial a nuestro clon:**
   ```bash
   git merge upstream/main
   ```
4. **Resolución de Conflictos:**
   Si modificaron el `Toolbar.tsx` o `layout.tsx` (donde pusimos nuestro botón), Git detectará un conflicto. Asegúrate de mantener tu componente `<HoltmontExportButton />` durante la resolución manual.
5. **Subida a Producción:**
   ```bash
   git push origin main
   ```
   Vercel o Render detectarán el push y redesplegarán automáticamente la versión moderna con nuestras modificaciones.

---

## 10. CONCLUSIONES Y SIGUIENTES PASOS

La arquitectura delineada en este documento asegura que la integración sea robusta, segregada y mantenible.

- **Desacoplamiento Tecnológico:** Al encapsular React/Next.js/WebGPU dentro de un iFrame independiente, protegemos la lógica de negocios y reactividad de Vue 3, evitando "choques de frameworks" (React vs Vue).
- **Rendimiento:** Al estar aislado, el motor de gráficos 3D puede devorar RAM y recursos de GPU sin bloquear o relentizar las animaciones y transiciones de los formularios en la app principal.
- **Portabilidad:** Si el día de mañana se requiere crear una aplicación separada solo para diseño 3D o móvil, el clon alojado en Vercel servirá perfectamente sin dependencia pesada del monolito de Holtmont.

**Plan de Ejecución Práctico para los desarrolladores:**
1. Crear el Fork en GitHub (10 mins).
2. Modificar el código React para incluir `HoltmontExportButton` e imprimir un `console.log` para depurar (30 mins).
3. Desplegar en Vercel y obtener la URL (15 mins).
4. Implementar el `<div v-if="currentView === 'PASCAL_DESIGNER'">` en `index.html` (45 mins).
5. Implementar el listener `postMessage` en el `setup()` de Vue (30 mins).
6. Ajustar el Pydantic Schema en FastAPI (10 mins).
7. Ajustar `sheets.py` para grabar el JSON (20 mins).

---

## 11. ANEXOS: SOLUCIÓN DE PROBLEMAS COMUNES (TROUBLESHOOTING)

**Problema 1: El Iframe se ve blanco o muestra un error de conexión.**
*Solución:* Revisa si tu navegador está bloqueando las cookies de terceros. Pascal Editor podría requerir LocalStorage para la persistencia inicial y las políticas estrictas de privacidad (como Safari o Brave) pueden bloquear iFrames. Si es así, prueba en Google Chrome estándar o asegúrate de que el despliegue cuenta con certificado HTTPS válido.

**Problema 2: `window.postMessage` no parece estar disparándose.**
*Solución:* Abre la consola de desarrollador del navegador (F12). Revisa tanto el contexto principal (`top`) como el contexto del iFrame. Comprueba en la pestaña "Network" si los scripts de React están fallando. Asegúrate que `window.parent` no sea `null`.

**Problema 3: Error de gspread o Google Sheets al guardar.**
*Solución:* Es altamente probable que el string JSON generado sea demasiado grande para una celda. Intenta generar un cuadrado de 2x2 en el editor y exportarlo. Si funciona con archivos pequeños y falla con grandes, has tocado el límite de 50,000 caracteres de Sheets. Deberás implementar el guardado por archivos locales en el servidor y almacenar la ruta en lugar del texto crudo.

---

## 12. GLOSARIO DE TÉRMINOS

- **WebGPU:** Una nueva API web que proporciona acceso directo al hardware gráfico de la computadora. Es más rápida y moderna que WebGL. Pascal Editor la usa para renderizar 3D veloz.
- **Zustand:** Librería de manejo de estados en React. Equivalente moderno y minimalista de Redux. Contiene los datos abstractos (coordenadas, paredes, texturas).
- **iFrame (Inline Frame):** Un documento HTML incrustado en otro documento HTML en una web. Ideal para incrustar widgets externos o aplicaciones autónomas.
- **postMessage:** API de los navegadores que permite comunicación cruzada (cross-origin) de manera segura. El único método estándar para enviar strings o JSONs entre un padre y su iFrame de dominios diferentes.
- **Fork:** Una copia personal completa de un repositorio ajeno. Permite hacer experimentaciones o modificaciones sin alterar el proyecto del autor original.
