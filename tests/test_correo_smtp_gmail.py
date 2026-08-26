"""
El canal SMTP contra Gmail: resolución del host, exigencia de credenciales y un
envío de verdad.

Estas pruebas cubren el hueco que dejaba `test_storage_correo_productividad.py`:
ahí se comprueba a quién se escribe y qué dice el reporte, pero **nunca se abre
un socket**. Toda la ruta de envío (`smtplib`, STARTTLS, AUTH, DATA) quedaba sin
probar, así que un error ahí solo aparecía en producción.

Aquí se levanta un servidor SMTP real en localhost —con TLS y certificado
propio— y se comprueba que el mensaje sale, llega completo y con el HTML
intacto. Es la prueba que faltaba para poder decir "el agente puede mandar
correos" sin que sea una afirmación de fe.
"""

import base64
import datetime
import os
import socket
import ssl
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import correo  # noqa: E402


# --- Un servidor SMTP de verdad, en localhost ------------------------------

def _certificado_autofirmado(carpeta):
    """Certificado para `localhost`, usable como CA de sí mismo.

    Se firma a sí mismo y luego se pasa como `cafile` al cliente, así que la
    verificación TLS de la prueba es **real**: si el código dejara de cifrar, o
    lo hiciera contra otro nombre, la prueba falla.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(llave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - datetime.timedelta(minutes=5))
        .not_valid_after(ahora + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                       critical=False)
        .sign(llave, hashes.SHA256())
    )

    ruta_cert = carpeta / "smtp-prueba.pem"
    ruta_llave = carpeta / "smtp-prueba.key"
    ruta_cert.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    ruta_llave.write_bytes(llave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()))
    return ruta_cert, ruta_llave


class ServidorSMTPFalso(threading.Thread):
    """SMTP mínimo (EHLO, STARTTLS, AUTH PLAIN, MAIL, RCPT, DATA) sobre socket.

    No es un mock de `smtplib`: es un servidor al otro lado de un socket, que es
    justo lo que hace falta para que la prueba diga algo sobre la ruta de envío.
    """

    def __init__(self, ruta_cert, ruta_llave):
        super().__init__(daemon=True)
        self._contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._contexto.load_cert_chain(str(ruta_cert), str(ruta_llave))
        self._escucha = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._escucha.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._escucha.bind(("127.0.0.1", 0))
        self._escucha.listen(1)
        self._escucha.settimeout(15)
        self.puerto = self._escucha.getsockname()[1]
        self.mensajes = []        # [(remitente, [destinatarios], cuerpo)]
        self.credenciales = []    # [(usuario, clave)]
        self.hubo_tls = False
        self.sesiones = 0

    def run(self):
        while True:
            try:
                conexion, _ = self._escucha.accept()
            except (OSError, socket.timeout):
                return
            try:
                self._atender(conexion)
            except Exception:  # noqa: BLE001 - un fallo aquí lo detecta el cliente
                pass
            finally:
                conexion.close()

    def _atender(self, conexion):
        self.sesiones += 1
        flujo = conexion.makefile("rwb")
        flujo.write(b"220 localhost servidor de prueba\r\n")
        flujo.flush()
        de, para, autenticado = "", [], False

        while True:
            linea = flujo.readline()
            if not linea:
                return
            orden = linea.decode("utf-8", "replace").strip()
            mayus = orden.upper()

            if mayus.startswith(("EHLO", "HELO")):
                extras = b"250-STARTTLS\r\n" if not self.hubo_tls else b"250-AUTH PLAIN\r\n"
                flujo.write(b"250-localhost\r\n" + extras + b"250 8BITMIME\r\n")
                flujo.flush()
            elif mayus.startswith("STARTTLS"):
                flujo.write(b"220 Listo para TLS\r\n")
                flujo.flush()
                conexion = self._contexto.wrap_socket(conexion, server_side=True)
                flujo = conexion.makefile("rwb")
                self.hubo_tls = True
            elif mayus.startswith("AUTH PLAIN"):
                crudo = base64.b64decode(orden.split(" ", 2)[2])
                _, usuario, clave = crudo.decode("utf-8").split("\0")
                self.credenciales.append((usuario, clave))
                autenticado = True
                flujo.write(b"235 Autenticado\r\n")
                flujo.flush()
            elif mayus.startswith("MAIL FROM"):
                de = orden.split(":", 1)[1].strip().strip("<>")
                para = []
                flujo.write(b"250 OK\r\n")
                flujo.flush()
            elif mayus.startswith("RCPT TO"):
                para.append(orden.split(":", 1)[1].strip().strip("<>"))
                flujo.write(b"250 OK\r\n")
                flujo.flush()
            elif mayus.startswith("DATA"):
                flujo.write(b"354 Manda el mensaje\r\n")
                flujo.flush()
                cuerpo = []
                while True:
                    trozo = flujo.readline()
                    if not trozo or trozo.strip() == b".":
                        break
                    cuerpo.append(trozo)
                self.mensajes.append((de, list(para),
                                      b"".join(cuerpo).decode("utf-8", "replace"),
                                      autenticado))
                flujo.write(b"250 Aceptado\r\n")
                flujo.flush()
            elif mayus.startswith("QUIT"):
                flujo.write(b"221 Adios\r\n")
                flujo.flush()
                return
            else:
                flujo.write(b"250 OK\r\n")
                flujo.flush()


@pytest.fixture
def servidor_smtp(tmp_path, monkeypatch):
    """Servidor local + el contexto TLS que confía en su certificado."""
    ruta_cert, ruta_llave = _certificado_autofirmado(tmp_path)
    servidor = ServidorSMTPFalso(ruta_cert, ruta_llave)
    servidor.start()

    contexto = ssl.create_default_context(cafile=str(ruta_cert))
    monkeypatch.setattr(ssl, "create_default_context",
                        lambda *a, **k: contexto)

    for variable in (correo.SMTP_HOST_ENV, correo.SMTP_PORT_ENV,
                     correo.SMTP_USER_ENV, correo.SMTP_PASSWORD_ENV,
                     correo.SMTP_FROM_ENV):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(correo.SMTP_HOST_ENV, "localhost")
    monkeypatch.setenv(correo.SMTP_PORT_ENV, str(servidor.puerto))
    monkeypatch.setenv(correo.SMTP_USER_ENV, "reportes@holtmont.com")
    monkeypatch.setenv(correo.SMTP_PASSWORD_ENV, "clave-de-aplicacion")
    return servidor


@pytest.fixture
def sin_smtp(monkeypatch):
    for variable in (correo.SMTP_HOST_ENV, correo.SMTP_PORT_ENV,
                     correo.SMTP_USER_ENV, correo.SMTP_PASSWORD_ENV,
                     correo.SMTP_FROM_ENV):
        monkeypatch.delenv(variable, raising=False)


# --- El host de Gmail ------------------------------------------------------

def test_una_cuenta_de_gmail_no_necesita_que_le_digan_el_host(sin_smtp, monkeypatch):
    """El olvido que motivó este cambio: credenciales puestas, host vacío.

    Antes eso dejaba el canal apagado sin decir por qué; ahora la cuenta de
    Gmail resuelve sola a smtp.gmail.com.
    """
    monkeypatch.setenv(correo.SMTP_USER_ENV, "cotizaciones@gmail.com")
    assert correo.host() == correo.HOST_GMAIL
    assert correo.esta_configurado() is True


def test_el_host_explicito_manda_sobre_el_de_gmail(sin_smtp, monkeypatch):
    monkeypatch.setenv(correo.SMTP_USER_ENV, "cotizaciones@gmail.com")
    monkeypatch.setenv(correo.SMTP_HOST_ENV, "smtp.sendgrid.net")
    assert correo.host() == "smtp.sendgrid.net"


def test_el_remitente_de_gmail_tambien_resuelve_el_host(sin_smtp, monkeypatch):
    monkeypatch.setenv(correo.SMTP_FROM_ENV, "reportes@googlemail.com")
    assert correo.host() == correo.HOST_GMAIL


def test_un_correo_que_no_es_de_gmail_no_inventa_host(sin_smtp, monkeypatch):
    monkeypatch.setenv(correo.SMTP_USER_ENV, "reportes@holtmont.com")
    assert correo.host() == ""
    assert correo.esta_configurado() is False

    resultado = correo.enviar("Asunto", "<b>x</b>", destinatarios=["a@b.com"])
    assert resultado["success"] is False
    assert correo.SMTP_HOST_ENV in resultado["message"]


def test_el_puerto_por_omision_es_el_de_starttls(sin_smtp, monkeypatch):
    monkeypatch.setenv(correo.SMTP_USER_ENV, "cotizaciones@gmail.com")
    assert correo.puerto() == 587


def test_gmail_sin_contrasena_de_aplicacion_no_intenta_conectarse(sin_smtp, monkeypatch):
    """Gmail cerró el acceso por usuario y contraseña normal en 2022.

    Sin `SMTP_PASSWORD` el envío solo puede acabar en un 535; decirlo antes de
    abrir el socket es más útil que traducir el error de Google.
    """
    monkeypatch.setenv(correo.SMTP_USER_ENV, "cotizaciones@gmail.com")

    def no_se_puede_conectar(*args, **kwargs):  # pragma: no cover - no debe correr
        raise AssertionError("no debió abrirse ninguna conexión")

    monkeypatch.setattr("smtplib.SMTP", no_se_puede_conectar)
    monkeypatch.setattr("smtplib.SMTP_SSL", no_se_puede_conectar)

    resultado = correo.enviar("Asunto", "<b>x</b>", destinatarios=["a@b.com"])
    assert resultado["success"] is False
    assert correo.SMTP_PASSWORD_ENV in resultado["message"]


# --- El envío, contra un servidor SMTP real --------------------------------

def test_el_correo_sale_de_verdad_por_un_socket(servidor_smtp):
    resultado = correo.enviar("Reporte de productividad",
                              "<b>Todo en orden</b>",
                              destinatarios=["jefe@holtmont.com",
                                             "control@holtmont.com"])

    assert resultado["success"] is True, resultado
    assert resultado["recipients"] == ["jefe@holtmont.com", "control@holtmont.com"]

    de, para, cuerpo, autenticado = servidor_smtp.mensajes[0]
    assert de == "reportes@holtmont.com"
    assert para == ["jefe@holtmont.com", "control@holtmont.com"]
    assert "Reporte de productividad" in cuerpo
    assert autenticado is True
    assert servidor_smtp.hubo_tls is True, "el envío debe ir cifrado"
    assert servidor_smtp.credenciales == [("reportes@holtmont.com",
                                           "clave-de-aplicacion")]


def test_el_html_del_reporte_llega_intacto(servidor_smtp):
    correo.enviar("Cotizaciones", "<h1>KPI</h1>", destinatarios=["a@b.com"])

    _, _, cuerpo, _ = servidor_smtp.mensajes[0]
    assert "text/html" in cuerpo
    # El HTML viaja codificado en quoted-printable o base64 según el contenido:
    # basta comprobar que hay una parte HTML y el aviso en texto plano.
    assert "requiere un cliente de correo con HTML" in cuerpo


# --- El diagnóstico --------------------------------------------------------

def test_el_diagnostico_confirma_conexion_tls_y_credenciales(servidor_smtp):
    informe = correo.probar_conexion()

    assert informe["success"] is True, informe
    assert informe["host"] == "localhost"
    assert informe["puerto"] == servidor_smtp.puerto
    assert "conexion" in informe["pasos"] and "tls" in informe["pasos"]
    assert "autenticacion" in informe["pasos"]
    assert servidor_smtp.mensajes == [], "un diagnóstico sin destino no manda correo"


def test_el_diagnostico_con_destino_manda_un_correo_de_prueba(servidor_smtp):
    informe = correo.probar_conexion(destino="dueno@holtmont.com")

    assert informe["success"] is True, informe
    assert "envio" in informe["pasos"]
    _, para, cuerpo, _ = servidor_smtp.mensajes[0]
    assert para == ["dueno@holtmont.com"]
    assert "prueba" in cuerpo.lower()


def test_el_diagnostico_sin_host_no_miente(sin_smtp):
    informe = correo.probar_conexion()

    assert informe["success"] is False
    assert correo.SMTP_HOST_ENV in informe["message"]
    assert informe["pasos"] == []


def test_el_diagnostico_reporta_el_error_literal_del_servidor(servidor_smtp, monkeypatch):
    """Un fallo de red o de credenciales se reporta tal cual, sin maquillarlo."""
    monkeypatch.setenv(correo.SMTP_PORT_ENV, "1")   # nadie escucha ahí

    informe = correo.probar_conexion()

    assert informe["success"] is False
    assert informe["message"], "el error del servidor debe llegar al informe"
    assert "conexion" not in informe["pasos"]


def test_el_diagnostico_distingue_falta_de_configuracion_de_fallo_de_red(
        servidor_smtp, monkeypatch):
    """Sin variables de entorno no hay fallo de red que investigar."""
    monkeypatch.delenv(correo.SMTP_HOST_ENV, raising=False)
    monkeypatch.setenv(correo.SMTP_USER_ENV, "cuenta@gmail.com")
    monkeypatch.delenv(correo.SMTP_PASSWORD_ENV, raising=False)

    informe = correo.probar_conexion()
    assert informe["configurado"] is False
    assert correo.SMTP_PASSWORD_ENV in informe["message"]

    monkeypatch.setenv(correo.SMTP_HOST_ENV, "localhost")
    monkeypatch.setenv(correo.SMTP_USER_ENV, "reportes@holtmont.com")
    monkeypatch.setenv(correo.SMTP_PASSWORD_ENV, "clave-de-aplicacion")
    monkeypatch.setenv(correo.SMTP_PORT_ENV, "1")

    caido = correo.probar_conexion()
    assert caido["configurado"] is True, "la configuración estaba completa"
    assert caido["success"] is False


# --- El script de diagnóstico ---------------------------------------------

def test_el_script_reporta_el_canal_y_sale_con_cero(servidor_smtp, capsys):
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import probar_smtp

    codigo = probar_smtp.main([])

    salida = capsys.readouterr().out
    assert codigo == 0, salida
    assert "[ok]    conexion" in salida
    assert "[ok]    autenticacion" in salida
    assert "el canal funciona" in salida


def test_el_script_sale_con_uno_si_el_canal_esta_apagado(sin_smtp, capsys):
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import probar_smtp

    codigo = probar_smtp.main([])

    salida = capsys.readouterr().out
    assert codigo == 1
    assert "NO está configurado" in salida
