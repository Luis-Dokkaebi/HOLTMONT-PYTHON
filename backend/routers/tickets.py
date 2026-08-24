"""
Router de `bug_tickets`, bajo `/api/v2` igual que `tasks`.

Un verbo por ruta: crear, listar, mover de estatus, agregar evidencia,
verificar su integridad, y los dos de avisos al reportante.

A propósito **no** existe ninguna que reciba `descripcion` o `evidencia` en
un PATCH — es la garantía, a nivel de superficie de API, de que ningún
camino reescribe lo que ya se reportó.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend.core.engine import DataEngine, construir_engine
from backend.core.errors import BackendError, ErrorDeMotor, SinMotorConfigurado
from backend.repositories.tickets import TicketNoEncontrado, TicketRepository
from backend.schemas.notificacion import MarcarLeidas
from backend.schemas.ticket import TicketUpdate, TicketWrite

router = APIRouter(prefix="/api/v2", tags=["tickets"])

# PostgREST no encuentra la tabla. `PGRST205` es el código actual ("Could not
# find the table in the schema cache"); `42P01` es el `undefined_table` de
# Postgres, que asoma cuando el error viene de la base y no del router de
# PostgREST.
CODIGOS_TABLA_FALTANTE = frozenset({"PGRST205", "PGRST202", "42P01"})

# La tabla está, pero no con las columnas que espera el repositorio. `PGRST204`
# es "Could not find the '<col>' column in the schema cache"; `42703` es el
# `undefined_column` de Postgres. Pasa cuando se aplicó una versión vieja del
# DDL: sin distinguirlo, este caso salía como un 502 genérico ("vuelve a
# intentarlo") que nunca se arregla por reintentar.
CODIGOS_COLUMNA_FALTANTE = frozenset({"PGRST204", "42703"})

# Permiso denegado. `42501` es `insufficient_privilege`; `PGRST301`/`PGRST302`
# son los de credencial inválida o ausente. `bug_tickets` y
# `ticket_notificaciones` llevan RLS encendida y SIN políticas
# (docs/DDL_PENDIENTE.sql §5 y §6): solo `service_role` las ignora, así que un
# backend configurado con la clave `anon` lee vacío pero **no puede insertar**.
CODIGOS_PERMISO = frozenset({"42501", "PGRST301", "PGRST302"})
ESTADOS_PERMISO = frozenset({401, 403})

# `PostgREST GET bug_tickets?select=folio...` → `bug_tickets`. Se usa el nombre
# de la tabla, y nada más del mensaje: la consulta cruda no viaja al cliente.
_TABLA_EN_MENSAJE = re.compile(r"PostgREST \w+ ([A-Za-z_][A-Za-z0-9_]*)")

MENSAJE_MOTOR_CAIDO = (
    "No se pudo consultar el sistema de tickets. Vuelve a intentarlo; si sigue "
    "fallando, avisa al equipo."
)

# Qué se le pide a cada tabla para darla por buena. No es la lista completa de
# columnas: son las que, si faltan, dejan el sistema roto de una forma que no se
# ve desde fuera. `ticket_notificaciones.nota` es el caso: sin ella los avisos
# siguen llegando —el repositorio los reinserta sin la nota— y la tabla parecía
# sana, mientras la nota de soporte se perdía en silencio.
TABLAS_DEL_SISTEMA = {
    "bug_tickets": ("folio",),
    "ticket_notificaciones": ("folio", "nota"),
}


def obtener_repositorio() -> TicketRepository:
    """Dependencia: un repositorio por petición, con el motor que toque."""
    try:
        engine: DataEngine = construir_engine()
    except SinMotorConfigurado as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TicketRepository(engine)


def _es_tabla_faltante(exc: BackendError) -> bool:
    if not isinstance(exc, ErrorDeMotor):
        return False
    if exc.codigo in CODIGOS_TABLA_FALTANTE:
        return True
    # PostgREST no siempre manda `code` en el cuerpo. El 404 basta como señal:
    # la ruta la arma el motor, no el cliente, así que un "no existe" solo
    # puede ser la tabla.
    return exc.estado == 404 or "respondió 404" in str(exc)


def _es_columna_faltante(exc: BackendError) -> bool:
    return isinstance(exc, ErrorDeMotor) and exc.codigo in CODIGOS_COLUMNA_FALTANTE


def _es_permiso_denegado(exc: BackendError) -> bool:
    if not isinstance(exc, ErrorDeMotor):
        return False
    if exc.codigo in CODIGOS_PERMISO:
        return True
    if exc.estado in ESTADOS_PERMISO:
        return True
    # Postgres nombra así la violación de RLS aunque el estado sea 400.
    return "row-level security" in exc.detalle.lower()


def _tabla_del_fallo(exc: BackendError) -> str:
    """Nombre de la tabla que rechazó la operación; `""` si no se puede saber."""
    encontrado = _TABLA_EN_MENSAJE.search(str(exc))
    return encontrado.group(1) if encontrado else ""


def _pista(exc: BackendError) -> str:
    """
    Código corto para que quien reporta pueda repetirlo al equipo.

    Es el código de PostgREST/Postgres o, si no vino, el estado HTTP. Nunca la
    consulta ni la URL: eso es lo que se filtró el 2026-08-13 y no debe volver.
    """
    if not isinstance(exc, ErrorDeMotor):
        return ""
    if exc.codigo:
        return f" [código: {exc.codigo}]"
    if exc.estado:
        return f" [código: HTTP {exc.estado}]"
    return ""


def _causa(exc: BackendError) -> str:
    """Etiqueta estable de la causa. La usa también `/tickets/diagnostico`."""
    if _es_tabla_faltante(exc):
        return "tabla_faltante"
    if _es_columna_faltante(exc):
        return "columna_faltante"
    if _es_permiso_denegado(exc):
        return "permiso_denegado"
    return "motor_caido"


def _mensaje_de_causa(causa: str, tabla: str) -> str:
    cual = f"la tabla `{tabla}`" if tabla else "una tabla del sistema de tickets"
    if causa == "tabla_faltante":
        return (
            f"El sistema de tickets todavía no está instalado en la base de datos: falta "
            f"crear {cual}. Aplicar el DDL de docs/DDL_PENDIENTE.sql §5 (`bug_tickets`) "
            "y §6 (`ticket_notificaciones`)."
        )
    if causa == "columna_faltante":
        return (
            f"{cual.capitalize()} existe pero le faltan columnas: se aplicó una versión "
            "vieja del esquema. Volver a aplicar el DDL de docs/DDL_PENDIENTE.sql §5 y §6. "
            "Reintentar no lo arregla."
        )
    if causa == "permiso_denegado":
        return (
            f"La base rechazó la operación sobre {cual} por permisos. Las tablas del "
            "sistema de tickets llevan RLS encendida y sin políticas "
            "(docs/DDL_PENDIENTE.sql §5 y §6), así que solo la clave de servicio puede "
            "escribir en ellas: revisar que `SUPABASE_KEY` sea la `service_role` del "
            "proyecto y no la `anon`, y que estén los GRANT del DDL. Reintentar no lo "
            "arregla."
        )
    return MENSAJE_MOTOR_CAIDO


def _fallo_de_motor(exc: BackendError) -> HTTPException:
    """
    Traduce un fallo del motor a una respuesta que le sirva a quien la lee.

    El detalle interno se registra pero **no viaja al cliente**: el 2026-08-13
    el dueño intentó reportar un bug y recibió en pantalla
    `PostgREST GET bug_tickets?select=folio&offset=0&limit=1000 respondió 404`,
    que no le dice qué hacer y además expone la consulta.

    Se separan cuatro causas porque piden acciones distintas, y porque las tres
    primeras **no se arreglan reintentando** — que es lo único que decía el
    mensaje genérico que quedó en pantalla el 2026-08-17:

    * falta la tabla (503): aplicar el DDL;
    * falta una columna (503): aplicar el DDL nuevo, el aplicado es viejo;
    * permiso denegado (503): la clave del backend no es `service_role`, o
      faltan los GRANT — con RLS encendida y sin políticas, la clave `anon` lee
      vacío pero no puede insertar, y ese es exactamente el caso que deja el
      formulario fallando para todo el mundo;
    * cualquier otra cosa (502): la base no responde, reintentar.
    """
    print(f"[tickets] fallo del motor: {exc} | detalle={getattr(exc, 'detalle', '')[:300]}")
    causa = _causa(exc)
    detalle = _mensaje_de_causa(causa, _tabla_del_fallo(exc)) + _pista(exc)
    return HTTPException(status_code=502 if causa == "motor_caido" else 503, detail=detalle)


class SolicitudTicket(BaseModel):
    ticket: TicketWrite
    reportado_por: str = Field(..., min_length=1)
    contexto: Optional[Dict[str, Any]] = None


class SolicitudEvidencia(BaseModel):
    """Mismo cuerpo que `/api/legacy/upload`: data URL, tipo y nombre."""

    data: str = Field(..., min_length=1)
    type: Optional[str] = None
    name: Optional[str] = None


@router.post("/tickets")
def crear_ticket(
    solicitud: SolicitudTicket = Body(...),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    try:
        creado = repo.crear(solicitud.ticket, solicitud.reportado_por, solicitud.contexto)
    except ErrorDeMotor as exc:
        raise _fallo_de_motor(exc) from exc
    except BackendError as exc:
        # Lo que sí es culpa de la petición: p. ej. sin usuario en sesión.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": creado.model_dump(mode="json")}


@router.get("/tickets")
def listar_tickets(
    estatus: Optional[str] = Query(None),
    modulo: Optional[str] = Query(None),
    reportado_por: Optional[str] = Query(None),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    try:
        tickets = repo.listar(estatus=estatus, modulo=modulo, reportado_por=reportado_por)
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
    return {
        "success": True,
        "data": [t.model_dump(mode="json") for t in tickets],
        "count": len(tickets),
    }


@router.get("/tickets/diagnostico")
def diagnosticar_sistema_de_tickets(
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    """
    Dice si el sistema de tickets puede operar, y qué falta si no.

    Existe porque cuando el formulario falla para todo el mundo, la causa real
    (falta el DDL, falta una columna, la clave no es `service_role`) solo vivía
    en los registros del despliegue, que nadie del equipo lee. Una lectura de
    una fila por tabla basta para distinguirlas.

    La lectura pide **las columnas que importan**, no solo `folio`
    (`TABLAS_DEL_SISTEMA`). Sin eso, una base a la que le falta
    `ticket_notificaciones.nota` se veía sana aquí mientras la nota de soporte
    se perdía en cada aviso.

    No devuelve credenciales ni datos de tickets: solo el nombre de la tabla,
    la causa y el código de la base.
    """
    tablas = []
    for tabla, columnas in TABLAS_DEL_SISTEMA.items():
        try:
            repo.engine.select(tabla, columnas=list(columnas), limite=1)
        except BackendError as exc:
            causa = _causa(exc)
            tablas.append({
                "tabla": tabla,
                "ok": False,
                "causa": causa,
                "codigo": getattr(exc, "codigo", "") or "",
                "que_hacer": _mensaje_de_causa(causa, tabla),
            })
        else:
            tablas.append({"tabla": tabla, "ok": True, "causa": "", "codigo": "", "que_hacer": ""})

    return {
        "success": True,
        "motor": getattr(repo.engine, "nombre", "desconocido"),
        "operativo": all(t["ok"] for t in tablas),
        "tablas": tablas,
    }


@router.patch("/tickets/{folio}")
def actualizar_ticket(
    folio: str,
    cambios: TicketUpdate = Body(...),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    try:
        actualizado = repo.actualizar_estatus(folio, cambios)
    except TicketNoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
    return {"success": True, "data": actualizado.model_dump(mode="json")}


@router.get("/tickets/{folio}/evidencia/verificacion")
def verificar_evidencia_del_ticket(
    folio: str,
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    """
    Comprueba que cada adjunto siga siendo el que se subió.

    Descarga el objeto y compara su hash con el `sha256` guardado al momento
    de subirlo. Existe porque la evidencia **no es inmutable** frente a la
    clave de servicio —medido el 2026-08-13: `PUT` con `x-upsert` y `DELETE`
    pasan pese a las políticas, porque `service_role` tiene BYPASSRLS, y
    Storage no ofrece object-lock—. No pudiendo impedir la alteración, esto
    es lo que permite demostrarla.

    `integra` es `true` solo si **todos** los adjuntos están intactos.
    """
    from api.services import storage

    try:
        ticket = repo.obtener(folio)
    except TicketNoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc

    resultados = [
        {"url": e.get("url"), **storage.verificar_evidencia(e.get("url"), e.get("sha256"))}
        for e in (ticket.evidencia or [])
    ]
    return {
        "success": True,
        "folio": ticket.folio,
        "integra": all(r.get("estado") == "intacta" for r in resultados),
        "evidencia": resultados,
    }


@router.get("/tickets/{folio}/evidencia/{indice}")
def abrir_evidencia_del_ticket(
    folio: str,
    indice: int,
    repo: TicketRepository = Depends(obtener_repositorio),
) -> RedirectResponse:
    """
    Abre el adjunto número `indice` del ticket: redirige a una URL firmada.

    Existe porque hasta ahora el panel enlazaba directo la URL guardada en
    `evidencia[].url`, que tiene forma pública (`/object/public/...`) mientras
    que el bucket de evidencia es **privado** a propósito
    (docs/DDL_PENDIENTE.sql §5). El resultado, en pantalla, era
    `{"statusCode":"404","error":"Bucket not found","code":"NoSuchBucket"}` en
    vez de la imagen — y no había forma de ver la evidencia de ningún ticket.

    La alternativa —hacer público el bucket— se descarta: publicaría la
    evidencia de todos los reportes a quien adivine la ruta. Aquí la firma se
    emite en el momento y caduca en `storage.SEGUNDOS_URL_FIRMADA`.

    El redirect (307) en vez de un JSON con la URL es deliberado: así el
    enlace del panel es un `<a href>` normal y un `<img src>` funciona sin
    JavaScript, y el archivo viaja del navegador a Storage sin pasar por esta
    función — un video de 50 MB no cabe en la respuesta de una serverless.

    Qué NO arregla, dicho en voz alta: esta ruta no comprueba quién llama, igual
    que el resto de la API (ver la nota de `api/main.py` sobre la autorización
    que vive solo en `/api/config`). Quien pueda listar tickets ya veía la URL
    del adjunto, así que esto no abre nada nuevo — y una firma de cinco minutos
    expone menos que la URL permanente que se guardaba antes—, pero cerrar esa
    puerta es un `Depends` de sesión para toda la API, no un cambio de aquí.
    """
    from api.services import storage

    try:
        ticket = repo.obtener(folio)
    except TicketNoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc

    evidencia = list(ticket.evidencia or [])
    if indice < 0 or indice >= len(evidencia):
        raise HTTPException(
            status_code=404,
            detail=f"El ticket {folio} no tiene evidencia número {indice}.",
        )

    item = evidencia[indice]
    firma = storage.url_firmada_evidencia(item.get("path") or item.get("url"))
    if not firma.get("success"):
        # 502 y no 404: el ticket y el adjunto existen; lo que falló es
        # Storage. El mensaje trae el nombre del bucket, que es lo que hace
        # falta saber si lo que pasa es que nunca se creó.
        raise HTTPException(status_code=502, detail=firma.get("message") or "No se pudo abrir la evidencia.")

    # 307 y no 302: preserva el método y, sobre todo, deja claro que la URL
    # de destino es temporal y no se debe cachear como permanente.
    return RedirectResponse(url=firma["url"], status_code=307)


@router.post("/tickets/{folio}/evidencia")
def agregar_evidencia(
    folio: str,
    solicitud: SolicitudEvidencia = Body(...),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    """
    Sube el archivo (bucket privado, whitelist, tope de tamaño — ver
    `api/services/storage.subir_evidencia_ticket`) y lo agrega al ticket.
    No hay parámetro para reemplazar un adjunto existente: la única
    operación posible aquí es añadir uno nuevo.
    """
    from api.services import storage

    subida = storage.subir_evidencia_ticket(folio, solicitud.data, solicitud.type, solicitud.name)
    if not subida.get("success"):
        raise HTTPException(status_code=400, detail=subida.get("message") or "No se pudo subir la evidencia.")

    item = {
        "url": subida["fileUrl"],
        # Ruta del objeto dentro del bucket. `url` tiene forma pública pero el
        # bucket es privado, así que esa URL NO abre el archivo (Storage
        # responde `NoSuchBucket`); quien lo abre es
        # `/tickets/{folio}/evidencia/{indice}`, que firma esta ruta al vuelo.
        "path": subida.get("path") or "",
        "tipo": subida["mime"],
        "sha256": subida["sha256"],
        "subido_en": datetime.now(timezone.utc).isoformat(),
    }
    try:
        actualizado = repo.agregar_evidencia(folio, item)
    except TicketNoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
    return {"success": True, "data": actualizado.model_dump(mode="json")}


# ======================================================================
# Avisos a quien reportó
# ======================================================================
# Van en este router y no en uno propio porque su ciclo de vida es el del
# ticket: no existen avisos que no vengan de un cambio de estatus.
#
# El canal es dentro de la plataforma, no correo. Medido sobre el
# organigrama: de 41 cuentas, solo 6 tienen correo registrado, así que un
# aviso por correo no le llegaría a 35 personas y fallaría en silencio.


@router.get("/notificaciones")
def listar_notificaciones(
    usuario: str = Query(..., min_length=1, description="Cuenta destinataria"),
    solo_no_leidas: bool = Query(False),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    try:
        avisos = repo.notificaciones.listar(usuario, solo_no_leidas=solo_no_leidas)
        no_leidas = repo.notificaciones.contar_no_leidas(usuario)
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
    return {
        "success": True,
        "data": [a.model_dump(mode="json") for a in avisos],
        "no_leidas": no_leidas,
    }


@router.post("/notificaciones/marcar-leidas")
def marcar_notificaciones_leidas(
    peticion: MarcarLeidas = Body(...),
    repo: TicketRepository = Depends(obtener_repositorio),
) -> Dict[str, Any]:
    """
    Marca avisos como leídos. Sin `ids`, marca todos los de esa persona.

    El destinatario se filtra siempre, también cuando vienen `ids`: una
    petición con el id de otra persona no puede marcarle sus avisos.
    """
    try:
        cuantas = repo.notificaciones.marcar_leidas(peticion.destinatario, peticion.ids)
        no_leidas = repo.notificaciones.contar_no_leidas(peticion.destinatario)
    except BackendError as exc:
        raise _fallo_de_motor(exc) from exc
    return {"success": True, "marcadas": cuantas, "no_leidas": no_leidas}
