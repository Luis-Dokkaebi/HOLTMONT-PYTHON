"""
Solicitud de cotización a un prospecto del mapa: el puente con el correo que ya existe.

No hay un segundo camino de envío. El correo sale por `api/services/correo.py`
—`enviar(asunto, html, destinatarios)` con `esta_configurado()` de guarda—, que
es el mismo canal SMTP por el que salen los reportes de los agentes. Aquí solo
se compone el mensaje y se comprueba que se pueda mandar.

⚠️ EL ENVÍO ESTÁ APAGADO, Y NO POR PRUDENCIA GENÉRICA
------------------------------------------------------
El DENUE es dato público y abierto del INEGI. Usar esos 7,324 correos para
**contacto comercial** no lo es: cae bajo la LFPDPPP, que exige que el mensaje
identifique a la empresa que lo manda y ofrezca una vía de baja. Ese texto es
una decisión del dueño, no del código (plan de prospección §11, punto 5), y a la
fecha de este módulo **no está definido**.

Por eso hay dos cerrojos y no uno:

  1. `AVISO_LFPDPPP` está vacío. Mientras lo esté, no se manda nada.
  2. `GEO_CORREO_HABILITADO` tiene que valer `1` en el entorno.

Son dos porque protegen de cosas distintas. La variable de entorno protege de un
despliegue apresurado; la constante vacía protege de que alguien encienda la
variable creyendo que el texto ya estaba. Encender solo la variable **no manda
nada**: sin el aviso legal no hay correo, y esa es la única garantía que no
depende de que nadie se acuerde.

Mientras tanto el módulo sí sirve: compone el mensaje y lo devuelve como vista
previa, para que quien prospecta lo copie y lo mande desde su propio cliente
—asumiendo él la responsabilidad, como hasta hoy—.
"""

from __future__ import annotations

import os
from html import escape
from typing import Any, Callable, Dict, Optional

from api.services import correo

# Texto legal de baja. Lo define el dueño (§11, punto 5). Vacío = no se envía.
AVISO_LFPDPPP: str = ""

BANDERA_ENVIO_ENV = "GEO_CORREO_HABILITADO"
VALORES_ENCENDIDO = frozenset({"1", "true", "si", "sí", "yes"})

MOTIVO_AVISO_PENDIENTE = "aviso_legal_pendiente"
MOTIVO_ENVIO_APAGADO = "envio_deshabilitado"
MOTIVO_SMTP = "smtp_no_configurado"
MOTIVO_SIN_DESTINATARIO = "sin_destinatario"


def aviso_definido() -> bool:
    """Si el texto legal de baja ya está escrito."""
    return bool(AVISO_LFPDPPP.strip())


def bandera_encendida() -> bool:
    return os.environ.get(BANDERA_ENVIO_ENV, "").strip().lower() in VALORES_ENCENDIDO


def envio_habilitado() -> bool:
    """Los tres cerrojos, en uno. Cualquiera apagado deja el envío bloqueado."""
    return aviso_definido() and bandera_encendida() and correo.esta_configurado()


def cuerpo_html(nombre: str, mensaje: str) -> str:
    """
    El correo, con el aviso legal pegado al final.

    El texto lo redacta el agente (`POST /api/geo/agente`) o lo escribe una
    persona; aquí llega ya escrito. Se escapa: viene de un LLM o de un teclado,
    y en los dos casos es entrada que no controla este módulo.
    """
    cuerpo = escape(mensaje or "").replace("\n", "<br>")
    pie = (f'<hr style="border:none;border-top:1px solid #ddd;margin:24px 0;">'
           f'<p style="font-size:11px;color:#777;line-height:1.5;">'
           f'{escape(AVISO_LFPDPPP)}</p>') if aviso_definido() else ""
    return (
        '<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;">'
        f'<p style="font-size:14px;color:#333;line-height:1.6;">{cuerpo}</p>'
        f'{pie}</div>'
    )


def _motivo_del_bloqueo(destinatario: str) -> Optional[str]:
    """Por qué no se puede mandar, o `None` si sí se puede. En orden de gravedad."""
    if not destinatario:
        return MOTIVO_SIN_DESTINATARIO
    if not aviso_definido():
        return MOTIVO_AVISO_PENDIENTE
    if not bandera_encendida():
        return MOTIVO_ENVIO_APAGADO
    if not correo.esta_configurado():
        return MOTIVO_SMTP
    return None


MENSAJES: Dict[str, str] = {
    MOTIVO_SIN_DESTINATARIO:
        "Este establecimiento no declaró correo en el DENUE: no hay a dónde escribir.",
    MOTIVO_AVISO_PENDIENTE:
        "El envío está bloqueado: falta definir el aviso de identificación y baja "
        "que exige la LFPDPPP para contacto comercial. Es una decisión del dueño "
        "(plan de prospección §11, punto 5). Abajo va el correo redactado para "
        "copiarlo y mandarlo a mano mientras tanto.",
    MOTIVO_ENVIO_APAGADO:
        f"El envío automático está apagado ({BANDERA_ENVIO_ENV} no está en 1). "
        "Abajo va el correo redactado para copiarlo.",
    MOTIVO_SMTP:
        "SMTP_HOST no está configurado en este despliegue: el correo no se envió.",
}


def solicitar_cotizacion(nombre: str, destinatario: Any, asunto: str, mensaje: str,
                         enviar: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Manda la solicitud de cotización, o explica por qué no y deja la vista previa.

    `enviar` se inyecta —igual que `plano.generar_plano` recibe su `llm`— para
    que las pruebas puedan verificar QUÉ se manda sin abrir un socket. No hay
    ninguna ruta en la que este módulo construya su propio cliente SMTP.

    Nunca lanza y nunca devuelve un éxito que no ocurrió: el bloqueo sale con
    `success: false`, un `motivo` que el frontend puede distinguir y el correo ya
    compuesto para copiarlo a mano.
    """
    correo_destino = str(destinatario or "").strip()
    html = cuerpo_html(nombre, mensaje)
    vista_previa = {"asunto": asunto, "destinatario": correo_destino, "html": html}

    motivo = _motivo_del_bloqueo(correo_destino)
    if motivo is not None:
        return {"success": False, "motivo": motivo,
                "message": MENSAJES[motivo], "vista_previa": vista_previa}

    despacho = (enviar or correo.enviar)(asunto, html, [correo_destino])
    if not despacho.get("success"):
        return {"success": False, "motivo": MOTIVO_SMTP,
                "message": despacho.get("message", "No se pudo enviar el correo."),
                "vista_previa": vista_previa}
    return {"success": True, "message": f"Solicitud enviada a {correo_destino}.",
            "destinatarios": despacho.get("recipients", [correo_destino])}
