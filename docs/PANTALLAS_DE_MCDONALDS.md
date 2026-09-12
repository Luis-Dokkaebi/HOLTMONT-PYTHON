# Pantallas de McDonald's

Televisiones colgadas que muestran la tabla de un ejecutivo. **Solo muestran.**
No capturan, no editan y no borran: eso se sigue haciendo en el Tracker.

Esa decisión la tomó Antonio y es la que hace que esto sea pequeño. Sin
escritura no hay concurrencia que resolver, ni permisos por fila, ni una segunda
copia de la capa de guardado. Se lee lo que el Tracker ya escribe, en las mismas
tablas `tasks` y `quotes` particionadas por `source_sheet`.

**No se creó ninguna tabla nueva, y no hace falta crear una por persona.** La
partición por persona ya existe desde que la clave de `quotes` es
`(folio, source_sheet)`.

## Cómo se monta una televisión

1. Abrir el navegador de la TV en:

   ```
   https://<el-dominio>/?pantalla=EDUARDO%20MANZANARES
   ```

2. Ponerlo en pantalla completa (F11 en la mayoría de los televisores con
   navegador; en un Chromecast o mini-PC, el modo kiosko del navegador).

3. Nada más. No hay que iniciar sesión ni dejar nada abierto.

### El nombre que va en la URL

Es el **nombre de la hoja**, no el nombre de usuario ni el nombre completo. Son
los mismos que usa el Tracker (`staff_name` en `api/services/organigrama.py`):

| Qué se quiere ver | Qué va en `?pantalla=` |
| --- | --- |
| Las actividades de una persona | `EDUARDO MANZANARES` |
| Las cotizaciones de un vendedor | `EDUARDO MANZANARES (VENTAS)` |
| El core de ventas de Antonia | `ANTONIA_VENTAS` |

Los espacios se escriben `%20` en la barra de direcciones, o se pegan tal cual y
el navegador los convierte.

## Qué se ve

Seis columnas, no las veintiuna de la hoja: a cuatro metros una tabla de
veintiuna no se lee, y una que no se lee no informa.

- **Tracker:** FOLIO · CONCEPTO · AVANCE · FECHA_ESTIMADA_FIN · PRIORIDAD · ESTATUS
- **Cotizaciones:** FOLIO · CLIENTE · CONCEPTO · AVANCE · F. ENTREGA · ESTATUS

Lo pendiente sale primero. Una pantalla que abre con lo que ya está al 100 %
gasta su única página en trabajo terminado.

Las filas que no caben no se pierden: se reparten en páginas y la televisión las
rota sola cada 15 segundos. Los datos se vuelven a pedir cada 30 segundos.

### El importe no se muestra

`MONTO` está fuera de las seis. La pantalla cuelga de una pared que ve todo el
piso y quien entre de visita. Si la empresa decide que sí, se enciende con
`PANTALLA_MOSTRAR_MONTO=1` en las variables de entorno del despliegue.

### "SIN ACTUALIZAR desde hace…"

Abajo a la derecha va la edad de los datos, y se pone en rojo pasados dos
minutos.

No es decoración. **Una pantalla que perdió la red se ve exactamente igual que
una al día**: la tabla sigue ahí, con buena pinta, mostrando lo de anteayer. Ese
contador es lo único que distingue una cosa de la otra. Si está en rojo, lo que
hay en pantalla no es de fiar — revisar el wifi de la televisión.

Los datos viejos se dejan a la vista en vez de borrarlos, porque un corte de un
segundo dejaría la pared en blanco. Lo que no se hace es fingir que son de ahora.

## Lo que hay que saber antes de colgarla

**La URL no pide contraseña, y tiene que ser así:** una televisión colgada no
puede teclear una. Quien tenga el enlace ve esa hoja. Eso ya era cierto de
`GET /api/data`, que el Tracker usa desde siempre — esta pantalla lo hace
visible, no lo estrena. Las tablas con credenciales (`profiles`, `users`) están
bloqueadas y responden 403.

Si en algún momento hay que cerrarlo, se cierra para las dos rutas a la vez:
comparten la misma puerta a propósito, porque dos copias de un control de acceso
se separan con el tiempo y la que se olvide es la que deja pasar.

**La pestaña se recarga sola cada hora.** Una pestaña encendida doce horas
acumula memoria y acaba muerta sin que nadie lo vea; la pared se queda con la
última imagen congelada. La recarga cuesta dos segundos de parpadeo.

## Dónde está el código

| Qué | Dónde |
| --- | --- |
| Preparado de los datos | `api/services/pantalla.py` |
| Ruta | `GET /api/pantalla?hoja=<HOJA>` en `api/main.py` |
| Vista | `index.html`, bloque `pantalla-tv` |
| Pruebas | `tests/test_pantalla.py`, `tests/test_pantalla_ui.py` |

Las reglas de negocio no se duplican aquí: qué hoja es de ventas lo decide
`tracker_rules.is_sales_sheet` y qué cuenta como 100 % de avance,
`tracker_rules.is_progress_complete`.
