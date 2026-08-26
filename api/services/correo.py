"""
Canal de correo para los reportes de los agentes.

Sustituye a `MailApp.sendEmail` de Apps Script, que usaba la cuenta de Google
del propietario del script. Aquí se manda por SMTP con credenciales de entorno;
si no están configuradas, no se envía y se dice — nunca se reporta un envío que
no ocurrió.

**Corrige el bug 🐛 de destinatarios del original.** `_sendAgentEmail` y
`_sendTrackerProductivityEmail` resuelven a quién escribir así:

    if (USER_DB['ADMIN_CONTROL'] && USER_DB['ADMIN_CONTROL'].email) ...

`ADMIN_CONTROL` es un **rol**, no una cuenta: no existe como llave de
`USER_DB`, así que la condición siempre es falsa y el reporte de productividad
nunca llegó a quien debía (JAIME_OLIVO y DIMAS_RAMOS, que son los que tienen ese
rol). Aquí los destinatarios se resuelven **por rol** contra los perfiles, que
es lo que el checklist del SSD pedía al migrarlo.
"""

from __future__ import annotations

import contextlib
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, Iterable, Iterator, List, Optional

SMTP_HOST_ENV = "SMTP_HOST"
SMTP_PORT_ENV = "SMTP_PORT"
SMTP_USER_ENV = "SMTP_USER"
SMTP_PASSWORD_ENV = "SMTP_PASSWORD"
SMTP_FROM_ENV = "SMTP_FROM"

# Servidor de Google Workspace / Gmail. Es el proveedor de correo de la empresa,
# así que una cuenta @gmail.com no necesita que además le digan el host: se
# deduce. Un `SMTP_HOST` explícito siempre gana, para no atar el despliegue a
# Google si mañana se cambia de proveedor.
HOST_GMAIL = "smtp.gmail.com"
PUERTO_STARTTLS = 587
PUERTO_SSL = 465
_DOMINIOS_GMAIL = ("gmail.com", "googlemail.com")


def _es_cuenta_de_gmail(direccion: str) -> bool:
    return direccion.strip().lower().endswith(
        tuple(f"@{dominio}" for dominio in _DOMINIOS_GMAIL))


def host() -> str:
    """
    Servidor SMTP a usar, o cadena vacía si el canal está apagado.

    Orden: `SMTP_HOST` si está puesto; si no, `smtp.gmail.com` cuando la cuenta
    configurada es de Gmail. Deducirlo evita el fallo silencioso más probable de
    este despliegue —credenciales cargadas y host olvidado, que dejaba el canal
    apagado sin que nadie mirara por qué—; no lo inventa para otros dominios,
    donde adivinar sería peor que no enviar.
    """
    explicito = os.environ.get(SMTP_HOST_ENV, "").strip()
    if explicito:
        return explicito
    cuenta = (os.environ.get(SMTP_USER_ENV, "").strip()
              or os.environ.get(SMTP_FROM_ENV, "").strip())
    return HOST_GMAIL if _es_cuenta_de_gmail(cuenta) else ""


def puerto() -> int:
    """587 (STARTTLS) por omisión; 465 conmuta a SSL directo en `enviar`."""
    crudo = os.environ.get(SMTP_PORT_ENV, "").strip()
    if not crudo:
        return PUERTO_STARTTLS
    try:
        return int(crudo)
    except ValueError:
        return PUERTO_STARTTLS


def esta_configurado() -> bool:
    return bool(host())


def remitente() -> str:
    return (os.environ.get(SMTP_FROM_ENV, "").strip()
            or os.environ.get(SMTP_USER_ENV, "").strip())


def destinatarios_por_rol(roles: Iterable[str]) -> List[str]:
    """
    Correos de todas las cuentas cuyo rol esté en `roles`.

    Resolver por rol y no por nombre de cuenta es justo la corrección del bug:
    añadir mañana un segundo ADMIN_CONTROL lo incluye sin tocar código, y no hay
    forma de escribir una llave que no existe.
    """
    from api.services.organigrama import PERFILES, perfil

    buscados = {str(r).upper().strip() for r in roles}
    correos = []
    for cuenta in PERFILES:
        datos = perfil(cuenta)
        if str(datos.get("role", "")).upper().strip() not in buscados:
            continue
        correo = str(datos.get("email") or "").strip()
        if correo and correo not in correos:
            correos.append(correo)
    return correos


def _credencial_que_falta(servidor_smtp: str, usuario: str, clave: str) -> str:
    """
    Mensaje de error si al proveedor le faltan credenciales, o "" si está bien.

    Solo Gmail se comprueba por adelantado, y con motivo: cerró el acceso con la
    contraseña normal de la cuenta en mayo de 2022, así que sin usuario y
    contraseña **de aplicación** el envío solo puede acabar en
    `535 Username and Password not accepted`. Decirlo antes de abrir el socket
    es más útil que devolver ese 535 y dejar que alguien lo interprete.
    """
    if servidor_smtp == HOST_GMAIL and not (usuario and clave):
        return (f"Gmail exige {SMTP_USER_ENV} y {SMTP_PASSWORD_ENV} "
                "(contraseña de aplicación de 16 caracteres, no la de la "
                "cuenta): no se envió nada.")
    return ""


def _mensaje(asunto: str, html: str, de: str, receptores: List[str]) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = de
    mensaje["To"] = ", ".join(receptores)
    # Cuerpo alternativo en texto: un cliente que no renderice HTML mostraría el
    # marcado en crudo.
    mensaje.set_content("Este reporte requiere un cliente de correo con HTML.")
    mensaje.add_alternative(html, subtype="html")
    return mensaje


@contextlib.contextmanager
def _sesion_smtp(servidor_smtp: str, numero_puerto: int) -> Iterator[smtplib.SMTP]:
    """
    Sesión SMTP ya cifrada: SSL directo en el 465, STARTTLS en cualquier otro.

    El contexto es `ssl.create_default_context()`, que **verifica el certificado
    del servidor**. `smtplib.starttls()` sin argumentos no lo hace —usa un
    contexto sin verificación—, de modo que la conexión "cifrada" aceptaba
    cualquier certificado, incluido el de un intermediario. Las credenciales de
    la cuenta viajan por ese canal justo después.
    """
    contexto = ssl.create_default_context()
    if numero_puerto == PUERTO_SSL:
        with smtplib.SMTP_SSL(servidor_smtp, numero_puerto, timeout=20,
                              context=contexto) as sesion:
            yield sesion
    else:
        with smtplib.SMTP(servidor_smtp, numero_puerto, timeout=20) as sesion:
            sesion.starttls(context=contexto)
            yield sesion


def enviar(asunto: str, html: str, destinatarios: Optional[List[str]] = None,
           roles: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """
    Manda un correo HTML. Nunca lanza: un fallo de correo no puede tumbar el
    agente que lo genera, igual que en el original.
    """
    receptores = list(destinatarios or [])
    if roles:
        receptores.extend(r for r in destinatarios_por_rol(roles) if r not in receptores)

    if not receptores:
        return {"success": False, "message": "Sin destinatarios configurados."}
    if not esta_configurado():
        return {"success": False,
                "message": f"{SMTP_HOST_ENV} no configurado: el reporte no se envió."}

    de = remitente()
    if not de:
        return {"success": False,
                "message": f"Falta {SMTP_FROM_ENV} o {SMTP_USER_ENV}."}

    servidor_smtp = host()
    numero_puerto = puerto()
    usuario = os.environ.get(SMTP_USER_ENV, "").strip()
    clave = os.environ.get(SMTP_PASSWORD_ENV, "")

    falta = _credencial_que_falta(servidor_smtp, usuario, clave)
    if falta:
        return {"success": False, "message": falta}

    mensaje = _mensaje(asunto, html, de, receptores)

    try:
        with _sesion_smtp(servidor_smtp, numero_puerto) as sesion:
            if usuario:
                sesion.login(usuario, clave)
            sesion.send_message(mensaje)
    except Exception as exc:  # noqa: BLE001
        print(f"[correo] No se pudo enviar '{asunto}': {exc}")
        return {"success": False, "message": str(exc)}

    return {"success": True, "recipients": receptores}


def probar_conexion(destino: Optional[str] = None) -> Dict[str, Any]:
    """
    Comprueba el canal de verdad: conecta, cifra, autentica y —si se le da un
    `destino`— manda un correo de prueba.

    Existe porque hasta ahora la única forma de saber si el SMTP estaba bien
    configurado era esperar al cron de las 07:00 y ver si llegaba el reporte. El
    informe dice **qué paso** se completó, así que un fallo señala el punto
    exacto: host mal escrito (no hay "conexion"), contraseña normal en vez de la
    de aplicación (no hay "autenticacion"), remitente rechazado (no hay "envio").

    Lo usa `scripts/probar_smtp.py`. Nunca lanza: devuelve el error literal del
    servidor, sin traducirlo ni suavizarlo.
    """
    servidor_smtp = host()
    numero_puerto = puerto()
    usuario = os.environ.get(SMTP_USER_ENV, "").strip()
    clave = os.environ.get(SMTP_PASSWORD_ENV, "")

    informe: Dict[str, Any] = {
        "success": False,
        "host": servidor_smtp,
        "puerto": numero_puerto,
        "usuario": usuario,
        "remitente": remitente(),
        # `configurado` separa "faltan variables de entorno" de "el servidor
        # falló": lo primero se arregla en el panel del despliegue, lo segundo
        # no, y confundirlos manda a buscar al sitio equivocado.
        "configurado": False,
        "pasos": [],
        "message": "",
    }

    if not servidor_smtp:
        informe["message"] = (
            f"{SMTP_HOST_ENV} no configurado y la cuenta tampoco es de Gmail: "
            "el canal está apagado y no se envía nada.")
        return informe

    falta = _credencial_que_falta(servidor_smtp, usuario, clave)
    if falta:
        informe["message"] = falta
        return informe

    de = remitente()
    if not de:
        informe["message"] = f"Falta {SMTP_FROM_ENV} o {SMTP_USER_ENV}."
        return informe

    informe["configurado"] = True

    try:
        with _sesion_smtp(servidor_smtp, numero_puerto) as sesion:
            informe["pasos"].append("conexion")
            informe["pasos"].append("tls")
            if usuario:
                sesion.login(usuario, clave)
                informe["pasos"].append("autenticacion")
            if destino:
                sesion.send_message(_mensaje(
                    "Prueba del canal de correo — Holtmont",
                    "<p>Prueba del canal SMTP. Si lees esto, los reportes de "
                    "los agentes pueden salir por este remitente.</p>",
                    de, [destino]))
                informe["pasos"].append("envio")
    except Exception as exc:  # noqa: BLE001
        informe["message"] = str(exc)
        return informe

    informe["success"] = True
    informe["message"] = (f"Canal listo por {servidor_smtp}:{numero_puerto}"
                          + (f"; correo de prueba enviado a {destino}." if destino
                             else "; no se envió ningún correo (falta --a)."))
    return informe


# --- Plantillas -------------------------------------------------------
# El original arma el HTML concatenando ~40 líneas por reporte. Aquí se reduce a
# una plantilla común con secciones, porque los dos correos (cotizaciones y
# productividad) comparten estructura: resumen de IA, tarjetas de KPI, tabla de
# alertas y tabla por persona.


def _tarjetas(kpis: List[tuple]) -> str:
    celdas = "".join(
        f'<td style="background:#fff;border:1px solid #ddd;border-radius:8px;'
        f'padding:15px;text-align:center;">'
        f'<div style="font-size:12px;color:#666;text-transform:uppercase;">{etiqueta}</div>'
        f'<div style="font-size:24px;font-weight:bold;color:#333;margin-top:5px;">{valor}</div>'
        f'</td>'
        for etiqueta, valor in kpis
    )
    # Tabla y no flexbox: Outlook no soporta flex y era el destino de estos
    # correos.
    return f'<table style="width:100%;border-spacing:8px;"><tr>{celdas}</tr></table>'


def _filas_alertas(alertas: List[Dict[str, Any]]) -> str:
    if not alertas:
        return ('<tr><td colspan="3" style="padding:8px 12px;color:#28a745;">'
                '✅ Sin alertas críticas este mes</td></tr>')
    colores = {"ALTA": "#dc3545", "MEDIA": "#fd7e14"}
    return "".join(
        f'<tr><td style="padding:6px 12px;">{a.get("icon", "")}</td>'
        f'<td style="padding:6px 12px;color:#333;">{a.get("mensaje", "")}</td>'
        f'<td style="padding:6px 12px;"><span style="background:'
        f'{colores.get(a.get("severity"), "#17a2b8")};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:11px;">{a.get("severity", "")}</span></td></tr>'
        for a in alertas
    )


def cuerpo_reporte(titulo: str, subtitulo: str, resumen_ia: str,
                   kpis: List[tuple], alertas: List[Dict[str, Any]],
                   tabla_html: str = "", color: str = "#2c3e50") -> str:
    """HTML del reporte de un agente."""
    resumen = (resumen_ia or "").replace("\n", "<br>")
    return (
        '<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;background:#fff;">'
        f'<div style="background:{color};color:#fff;padding:24px;">'
        f'<h1 style="margin:0;font-size:22px;">{titulo}</h1>'
        f'<p style="margin:4px 0 0;font-size:13px;opacity:0.8;">{subtitulo}</p>'
        '</div>'
        '<div style="padding:24px;border:1px solid #eee;">'
        '<h2 style="font-size:16px;color:#444;border-bottom:2px solid '
        f'{color};padding-bottom:5px;">Resumen Ejecutivo (IA)</h2>'
        '<div style="background:#f8f9fa;padding:15px;border-radius:6px;color:#333;'
        f'font-size:14px;line-height:1.6;border-left:4px solid {color};">{resumen}</div>'
        f'{_tarjetas(kpis)}'
        '<h2 style="font-size:16px;color:#444;margin-top:24px;">Alertas</h2>'
        f'<table style="width:100%;border-collapse:collapse;">{_filas_alertas(alertas)}</table>'
        f'{tabla_html}'
        '</div></div>'
    )
