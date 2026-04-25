# Instrucciones para Actualizar el Fork de Pascal Editor

Dado que hiciste el Fork directamente desde el repositorio original en GitHub hacia tu cuenta (`holtmont-3d-editor`), ahora mismo tienes el código de Pascal Editor intacto. Necesitamos inyectarle la comunicación para que pueda hablar con tu página web de REAL-HOLTMONT.

Sigue estos 3 pasos para modificar el código de tu Fork.

---

## PASO 1: Crear el Botón de "Guardar en Holtmont"

Debemos crear un componente nuevo en la carpeta de la interfaz de usuario.

1. En tu repositorio `holtmont-3d-editor`, navega a la siguiente ruta:
   `packages/editor/src/components/ui/`
2. En esa carpeta, crea un **nuevo archivo** llamado:
   `HoltmontExportButton.tsx`
3. Abre ese archivo, copia el siguiente código y pégalo allí. Guarda los cambios.

```tsx
import React, { useCallback, useState } from 'react';
import { useScene } from '@pascal-app/core';

export const HoltmontExportButton: React.FC = () => {
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = useCallback(() => {
    setIsExporting(true);
    try {
      const nodes = useScene.getState().nodes;
      const rootNodeIds = useScene.getState().rootNodeIds;
      const collections = useScene.getState().collections;

      const projectData = {
        nodes,
        rootNodeIds,
        collections
      };

      const payload = {
        type: 'HOLTMONT_3D_EXPORT',
        data: projectData,
        version: '1.0',
        timestamp: new Date().toISOString()
      };

      window.parent.postMessage(payload, '*');

      if (window.top !== window.self) {
        // Just silently pass, since parent will show alert
      } else {
        alert('Diseño exportado correctamente a REAL-HOLTMONT');
      }
    } catch (error) {
      console.error('Error exportando diseño 3D', error);
      alert('Hubo un error al exportar el diseño.');
    } finally {
      setIsExporting(false);
    }
  }, []);

  return (
    <button
      onClick={handleExport}
      disabled={isExporting}
      title="Guardar en Holtmont"
      style={{
        backgroundColor: '#0056b3',
        color: 'white',
        border: 'none',
        padding: '0 12px',
        height: '28px',
        borderRadius: '6px',
        fontSize: '12px',
        fontWeight: '600',
        cursor: isExporting ? 'not-allowed' : 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '6px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
        <polyline points="17 21 17 13 7 13 7 21"></polyline>
        <polyline points="7 3 7 8 15 8"></polyline>
      </svg>
      {isExporting ? 'Guardando...' : 'Guardar'}
    </button>
  );
};
```

---

## PASO 2: Agregar el Botón a la Barra de Herramientas

Ahora vamos a hacer que el botón se vea en la pantalla.

1. En tu repositorio, abre el archivo:
   `packages/editor/src/components/ui/viewer-toolbar.tsx`
2. Ve al inicio del archivo, debajo de la importación `import { cn } from '../../lib/utils'`, agrega esta línea:
   ```tsx
   import { HoltmontExportButton } from "./HoltmontExportButton"
   ```
3. Ahora baja hasta el final del archivo y busca la función `ViewerToolbarLeft`. Debería verse así:
   ```tsx
   export function ViewerToolbarLeft() {
     return (
       <>
         <CollapseSidebarButton />
         <ViewModeControl />
       </>
     )
   }
   ```
4. Añade nuestro botón para que quede así:
   ```tsx
   export function ViewerToolbarLeft() {
     return (
       <>
         <HoltmontExportButton />
         <CollapseSidebarButton />
         <ViewModeControl />
       </>
     )
   }
   ```
5. Guarda el archivo.

---

## PASO 3: Permitir la Carga de Diseños Anteriores

Finalmente, tenemos que hacer que el editor escuche cuando REAL-HOLTMONT le mande de vuelta un diseño que guardaste días atrás.

1. Abre el archivo:
   `apps/editor/app/layout.tsx`
2. En la parte superior, agrega estas dos importaciones debajo de `import localFont from 'next/font/local'`:
   ```tsx
   import { useEffect } from 'react'
   import { useScene } from '@pascal-app/core'
   ```
3. Busca la función principal `export default function RootLayout({ children }) {`. Justo adentro de ella, pega este bloque `useEffect`:
   ```tsx
   export default function RootLayout({
     children,
   }: Readonly<{
     children: React.ReactNode
   }>) {

     useEffect(() => {
       const handleIncomingMessage = (event: MessageEvent) => {
         if (event.data && event.data.type === 'HOLTMONT_3D_IMPORT') {
           console.log('Recibiendo payload de diseño desde base de datos Holtmont', event.data.projectData);
           try {
             if (event.data.projectData && event.data.projectData.nodes) {
                console.log("Found nodes to load. Injecting to store...");
                useScene.setState({
                   nodes: event.data.projectData.nodes,
                   rootNodeIds: event.data.projectData.rootNodeIds,
                   collections: event.data.projectData.collections
                });
             }
           } catch (err) {
              console.error("Error al inyectar diseño en el canvas:", err);
           }
         }
       };
       window.addEventListener('message', handleIncomingMessage);
       return () => window.removeEventListener('message', handleIncomingMessage);
     }, []);

     return (
   // ...resto del codigo
   ```
4. Guarda el archivo.


---
## PASO FINAL: Subir a Vercel y enlazarlo.

1. Has un "commit" de estos cambios en tu GitHub (botón verde de "Commit changes").
2. Entra a Vercel.com, "Add New Project", selecciona tu `holtmont-3d-editor` y dale a "Deploy".
3. Toma la URL que te de Vercel.
4. En el código de **nuestra web actual**, abre el archivo `index.html` y cambia la variable (alrededor de la línea 4430):
   ```javascript
   const pascalEditorUrl = Vue.ref('PÁGA_AQUÍ_TU_URL_DE_VERCEL');
   ```
5. ¡Eso es todo! La integración estará terminada.