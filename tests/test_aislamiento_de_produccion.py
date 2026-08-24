"""
El `.env` del disco no puede meter una credencial de producción en la suite.

Por qué existe esta prueba
--------------------------
`tests/conftest.py` promete que ninguna prueba toca la base de producción, y lo
hacía sacando `SUPABASE_URL`, `SUPABASE_KEY` y `DATABASE_URL` de `os.environ` al
empezar la sesión. La promesa tenía dos agujeros, y los dos se abren solos en la
máquina de cualquiera que además use la aplicación en local:

1. **`api/main.py` vuelve a llenar lo que `conftest` vació.** Al importarse
   ejecuta `load_env_file(".env")`, que copia el archivo a `os.environ` saltando
   solo las claves **ya presentes**. Como `conftest` las había *sacado*, dejaban
   de estar presentes, y `.env` las reponía — con los valores de producción. La
   protección se desactivaba justo por haber actuado.

2. **`AGENTE_SQL_DATABASE_URL` no estaba en la lista.** Y esa no pasa por
   `construir_engine()`: `agente_sql.ejecutor_disponible()` la lee directa y
   prefiere esa conexión sobre el motor de la aplicación. O sea que el
   `BACKEND_ENGINE=memoria` que fija `conftest` —lo que salva a todo lo demás—
   no la alcanza. Con un `.env` lleno, `tests/test_agente_sql.py` abría un pool
   real contra Supabase y le mandaba sus `SELECT`.

El arreglo es dejar las claves **presentes y vacías** en vez de sacarlas. Todo
el código las lee con `os.environ.get(clave, "").strip()` —`backend/core/config.py`
lo documenta y `tests/test_api_contract.py` lo verifica—, así que una cadena
vacía significa "no configurada"; y estar presentes es lo que hace que
`load_env_file` las salte.

Esto NO afloja ninguna puerta: cierra una que se podía abrir sin querer.
"""

import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Las credenciales que jamás deben tener valor durante la suite. Son las tres
# que `conftest` ya cuidaba más la propia del agente de consultas.
CLAVES_PROTEGIDAS = (
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "DATABASE_URL",
    "AGENTE_SQL_DATABASE_URL",
)


@pytest.mark.parametrize("clave", CLAVES_PROTEGIDAS)
def test_la_credencial_esta_presente_y_vacia(clave):
    """
    Presente **y** vacía, y las dos mitades importan: vacía para que el código
    la lea como "no configurada", y presente para que `load_env_file` no la
    tome por hueco que rellenar.
    """
    assert clave in os.environ, (
        f"{clave} no está en os.environ: `.env` la puede rellenar con el valor "
        f"de producción en cuanto se importe api/main.py."
    )
    assert os.environ[clave].strip() == "", (
        f"{clave} trae un valor durante la suite: {clave} apunta a una base real."
    )


def test_un_env_en_disco_no_puede_reinyectar_una_credencial(tmp_path):
    """
    El mecanismo, ejercido de verdad: se le da a `load_env_file` un `.env` con
    una cadena de producción y se comprueba que no entra.
    """
    from api.main import load_env_file

    archivo = tmp_path / ".env"
    archivo.write_text(
        "AGENTE_SQL_DATABASE_URL=postgresql://usuario:clave@base.produccion:6543/postgres\n"
        "SUPABASE_URL=https://produccion.supabase.co\n",
        encoding="utf-8",
    )

    previos = {c: os.environ.get(c) for c in CLAVES_PROTEGIDAS}
    try:
        load_env_file(str(archivo))
        assert os.environ["AGENTE_SQL_DATABASE_URL"].strip() == ""
        assert os.environ["SUPABASE_URL"].strip() == ""
    finally:
        for clave, valor in previos.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor


def test_el_agente_de_consultas_no_abre_una_conexion_propia():
    """
    La consecuencia que se quiere evitar, comprobada donde ocurría: el agente
    prefiere `AGENTE_SQL_DATABASE_URL` sobre el motor de la aplicación, así que
    es el único camino que `BACKEND_ENGINE=memoria` no cubre.
    """
    from api.services import agente_sql as ag

    ag._MOTORES.clear()
    try:
        ag.ejecutor_disponible()
        assert ag._MOTORES == {}, (
            f"El agente abrió un pool contra {list(ag._MOTORES)} durante la suite."
        )
    finally:
        ag._MOTORES.clear()


# Lo que hace que una variable sea una credencial o un extremo privado, por su
# nombre. `SMTP_PORT=587` y `PORT=8000` son valores por defecto públicos y
# deben poder seguir escritos en el ejemplo.
MARCAS_DE_SECRETO = ("KEY", "TOKEN", "SECRET", "PASSWORD", "URL", "DSN", "WEBHOOK")


def test_el_env_de_ejemplo_no_trae_ninguna_credencial():
    """
    `.env.example` se versiona. Su primera línea dice que nunca lleve valores
    reales; esto lo comprueba en vez de confiarlo.
    """
    raiz = pathlib.Path(__file__).resolve().parent.parent
    culpables = []
    for linea in (raiz / ".env.example").read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        if valor.strip() and any(m in clave.upper() for m in MARCAS_DE_SECRETO):
            culpables.append(clave)
    assert culpables == [], (
        f"{culpables} traen valor en .env.example, que es un archivo versionado: "
        f"eso es una credencial en el repositorio."
    )
