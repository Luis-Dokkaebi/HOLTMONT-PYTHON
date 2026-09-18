# -*- coding: utf-8 -*-
"""
Fichas del personal: nombre completo, puesto y foto.

`FICHAS` (api/services/organigrama.py) es la transcripción del documento de RH
"FOTOS CON PUESTO DE TRABAJO" (11 páginas, 31 personas). `ESPERADO` de este
archivo es esa misma transcripción escrita a mano, igual que `EXPECTED` en
`test_organigrama.py` es la del organigrama en papel: si alguien edita el
catálogo sin tener el documento delante, estas pruebas lo detienen.

Lo que se verifica y por qué:

* **Nadie de más y nadie de menos** (31 fichas, con su puesto literal). El
  puesto NO se normaliza: "Compras", "Calculo Estructural" y "Coordinador
  Electromecanica" están así en el documento.
* **Cada foto es un archivo que existe y es un JPEG.** Una ruta rota deja la
  tarjeta sin imagen y nadie se entera hasta que alguien abre el directorio.
* **Cada foto se usa una sola vez.** El documento pone dos y hasta cuatro
  personas por página; una foto repetida significa que el emparejamiento
  foto↔nombre se corrió, que es el error caro de esta tarea: ponerle a alguien
  la cara de otro.
* **Las claves son nombres del organigrama**, que es como el directorio y
  `people` nombran a la persona.
* **El endpoint solo sirve lo que está en el catálogo** (R7: nada de travesía
  de rutas por `/fotos/`).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import organigrama  # noqa: E402
from api.services.organigrama import (  # noqa: E402
    FICHAS,
    FOTOS_PUBLICAS,
    INITIAL_DIRECTORY,
    enriquecer_directorio,
    ficha,
    perfil,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_FOTOS = os.path.join(RAIZ, "api", "static", "fotos")
INDEX_HTML = os.path.join(RAIZ, "index.html")

# --- Transcripción del documento de RH ---------------------------------
# nombre del organigrama -> (nombre completo como lo escribe RH, puesto)
ESPERADO = {
    "DIMAS ELIEL RAMOS GARCIA": ("Dimas Eliel Ramos García", "Coordinador de Recursos Humanos"),
    "LAURA EDITH HUERTA ROCHA": ("Laura Edith Huerta Rocha", "Especialista en Nominas"),
    "FRANCISCO SANCHEZ SERNA": ("Francisco Sánchez Serna", "Auxiliar Recursos Humanos"),
    "LILIANA AYLIN MARTINEZ IBARRA": ("Liliana Aylin Martínez Ibarra", "Auxiliar Recursos Humanos"),
    "SONIA GARCIA PEREZ": ("Sonia Pérez García", "Compras"),
    "VANESSA DE LARA": ("Vanessa Rodríguez de Lara", "Auxiliar de compras"),
    "JUDITH ECHAVARRIA": ("Cristian Judith Echavarria Rodríguez", "Compras"),
    "ANGEL SALINAS": ("José Ángel Salinas Ramírez", "Diseño"),
    "EDGAR URIMAR LOPEZ MALDONADO": ("Edgar Urimar López Maldonado", "Calculo Estructural"),
    "TERESA GARZA": ("María Teresa Hernández Garza", "Precios Unitarios"),
    "GERALDINE MARTINEZ HERNANDEZ": ("Geraldine Marie Martínez Hernández",
                                     "Auxiliar Técnico en precios unitarios"),
    "EDUARDO BENITEZ": ("Eduardo Israel Benitez García", "Coordinador de Limpieza y Jardinería"),
    "CARLOS MENDEZ": ("Carlos Méndez Urbina", "Calidad"),
    "ROLANDO MORENO": ("Jesús Rolando Moreno Pérez", "Auxiliar Administrativo HVAC"),
    "EMILIANO ARREDONDO GOMEZ": ("Emiliano Arredondo Gómez", "Técnico HVAC"),
    "JEHU MARTINEZ": ("Martínez Montes Jehu Arsenio", "Auxiliar Administrativo Electromecánica"),
    "MIGUEL GALLARDO": ("Miguel Ángel Gallardo Jaramillo", "Coordinador Electromecanica"),
    "SEBASTIAN PADILLA": ("Erick Sebastián Padilla Carrillo", "Ventas Electromecánica"),
    "EDUARDO TERAN": ("Jesús Eduardo Teran García", "Coordinador de presupuestos"),
    "ANTONIA PINEDA LOPEZ": ("Antonia Pineda López", "Auxiliar de presupuestos"),
    "EDUARDO MANZANARES": ("Eduardo Manzanares Sanchez", "Coordinador HVAC"),
    "RAMIRO RODRIGUEZ": ("Ramiro Rodríguez Escalante", "Ventas construcción"),
    "RUBI MORENO RODRIGUEZ": ("Rubi Arelly Moreno Rodríguez", "Supervisor de Seguridad"),
    "JAIME OLIVO": ("Jaime Antonio Olivo Guerrero", "Superintendente de construcción"),
    "RICARDO MENDO": ("Ricardo Alonso Mendo Morales", "Residente de obra"),
    "ALFONSO CORREA": ("Alfonso Correa de Leon", "Supervisor de Obra"),
    "CESAR EDUARDO GARCIA AVALOS": ("Cesar Eduardo García Avalos", "Supervisor de Obra"),
    "JUANA MARIA RODRIGUEZ JUAREZ": ("Juana María Rodríguez Juarez", "Coordinador de Finanzas"),
    "ROCIO ABIGAIL CASTRO COVARRUBIAS": ("Rocio Abigail Castro Covarrubias", "Facturación"),
    "ZAIRA YAZMIN AGUILAR AGUILON": ("Zaira Yazmin Aguilar Aguilon", "Auxiliar de finanzas"),
    "DANIA LIZBETH GONZALEZ LORES": ("Dania Lizbeth González Lores", "Auxiliar de finanzas"),
}


def test_estan_las_31_personas_del_documento_y_nadie_mas():
    assert sorted(FICHAS) == sorted(ESPERADO), (
        "El catálogo de fichas no coincide con el documento de RH: "
        f"sobran {sorted(set(FICHAS) - set(ESPERADO))}, "
        f"faltan {sorted(set(ESPERADO) - set(FICHAS))}"
    )


@pytest.mark.parametrize("clave", sorted(ESPERADO))
def test_cada_ficha_trae_el_nombre_y_el_puesto_literales(clave):
    nombre, puesto = ESPERADO[clave]
    assert FICHAS[clave]["nombre"] == nombre
    assert FICHAS[clave]["puesto"] == puesto


@pytest.mark.parametrize("clave", sorted(ESPERADO))
def test_la_foto_existe_y_es_un_jpeg(clave):
    ruta_publica = FICHAS[clave]["foto"]
    assert ruta_publica.startswith("/fotos/"), ruta_publica
    archivo = os.path.join(DIR_FOTOS, ruta_publica.rsplit("/", 1)[-1])
    assert os.path.exists(archivo), f"{clave}: no existe {archivo}"
    with open(archivo, "rb") as fh:
        cabecera = fh.read(3)
    # Marca de JPEG. El endpoint declara `image/jpeg`; si el archivo fuera un
    # PNG renombrado, el navegador lo toleraria pero la declaracion mentiria.
    assert cabecera == b"\xff\xd8\xff", f"{clave}: {archivo} no es un JPEG"
    assert os.path.getsize(archivo) > 1024, f"{clave}: {archivo} pesa casi nada"


def test_ninguna_foto_esta_repetida():
    """Una foto en dos fichas = el emparejamiento foto↔nombre se corrió."""
    rutas = [datos["foto"] for datos in FICHAS.values()]
    repetidas = {r for r in rutas if rutas.count(r) > 1}
    assert not repetidas, f"fotos asignadas a más de una persona: {sorted(repetidas)}"


def test_no_hay_fotos_huerfanas_en_el_directorio():
    """Un archivo que nadie referencia es peso muerto que igual se despliega."""
    en_disco = {f for f in os.listdir(DIR_FOTOS) if not f.startswith(".")}
    assert en_disco == set(FOTOS_PUBLICAS), (
        f"sin ficha que las use: {sorted(en_disco - set(FOTOS_PUBLICAS))}; "
        f"referenciadas pero ausentes: {sorted(set(FOTOS_PUBLICAS) - en_disco)}"
    )


def test_las_claves_son_nombres_del_organigrama():
    """
    La ficha se busca por el nombre del directorio (`people.nombre`). Una clave
    que no exista ahí es una ficha que nunca se va a mostrar.
    """
    del_organigrama = {persona["name"] for persona in INITIAL_DIRECTORY}
    huerfanas = sorted(set(FICHAS) - del_organigrama)
    assert not huerfanas, f"claves que no están en el organigrama: {huerfanas}"


# --- Resolución por cuenta ---------------------------------------------
@pytest.mark.parametrize(
    "cuenta,nombre,puesto",
    [
        # Por `staff_name`, que es el caso normal.
        ("DIMAS_RAMOS", "Dimas Eliel Ramos García", "Coordinador de Recursos Humanos"),
        ("SEBASTIAN_PADILLA", "Erick Sebastián Padilla Carrillo", "Ventas Electromecánica"),
        ("ANTONIA_VENTAS", "Antonia Pineda López", "Auxiliar de presupuestos"),
        ("INGE_OLIVO", "Jaime Antonio Olivo Guerrero", "Superintendente de construcción"),
        # Cuenta de control: no tiene `staff_name`, se reconoce por `label`.
        ("JAIME_OLIVO", "Jaime Antonio Olivo Guerrero", "Superintendente de construcción"),
    ],
)
def test_el_perfil_trae_nombre_puesto_y_foto(cuenta, nombre, puesto):
    p = perfil(cuenta)
    assert p["nombre"] == nombre
    assert p["puesto"] == puesto
    assert p["foto"].startswith("/fotos/")


def test_las_dos_cuentas_de_zaira_comparten_ficha():
    """`SAIRA` y `ZAIRA_AGUILAR` son la misma persona con dos cuentas."""
    assert perfil("SAIRA")["foto"] == perfil("ZAIRA_AGUILAR")["foto"]
    assert perfil("SAIRA")["puesto"] == "Auxiliar de finanzas"


def test_una_cuenta_sin_ficha_no_se_rompe():
    """
    El documento cubre 31 personas y el sistema tiene más cuentas. Quien no
    aparece se queda sin foto y sin puesto, pero con `nombre` —su `label`— para
    que la vista tenga siempre qué mostrar.
    """
    p = perfil("LUIS_CARLOS")
    assert p["foto"] == ""
    assert p["puesto"] == ""
    assert p["nombre"] == "Luis Carlos Holt Montero"


def test_una_cuenta_desconocida_sigue_devolviendo_vacio():
    """Comportamiento del original (`USER_DB[...] || {}`): no se inventa perfil."""
    assert perfil("NO_EXISTE") == {}
    assert perfil("") == {}


def test_la_ficha_de_alguien_sin_documento_es_vacia():
    assert ficha("DANIELA CASTRO") == {}
    assert ficha(None) == {}


def test_profiles_manda_sobre_la_transcripcion(monkeypatch):
    """
    La tabla que el dueño puede editar sin desplegar gana. Si mañana `profiles`
    trae `foto`/`puesto`, la transcripción de RH pasa a ser el respaldo.
    """
    organigrama.reset_cache_perfiles()
    monkeypatch.setattr(
        organigrama,
        "_filas_profiles",
        lambda: [{
            "username": "DIMAS_RAMOS",
            "role": "ADMIN_CONTROL",
            "puesto": "Director de Recursos Humanos",
            "foto": "/fotos/otra.jpg",
        }],
    )
    p = perfil("DIMAS_RAMOS")
    assert p["puesto"] == "Director de Recursos Humanos"
    assert p["foto"] == "/fotos/otra.jpg"
    organigrama.reset_cache_perfiles()


def test_profiles_sin_las_columnas_cae_a_la_transcripcion(monkeypatch):
    """Hoy la tabla no tiene esas columnas: la ficha las rellena igual."""
    organigrama.reset_cache_perfiles()
    monkeypatch.setattr(
        organigrama,
        "_filas_profiles",
        lambda: [{"username": "DIMAS_RAMOS", "role": "ADMIN_CONTROL",
                  "staff_name": "DIMAS ELIEL RAMOS GARCIA"}],
    )
    p = perfil("DIMAS_RAMOS")
    assert p["puesto"] == "Coordinador de Recursos Humanos"
    assert p["foto"] == "/fotos/dimas-eliel-ramos-garcia.jpg"
    organigrama.reset_cache_perfiles()


# --- Directorio ---------------------------------------------------------
def test_enriquecer_directorio_no_toca_el_nombre_canonico():
    """
    `name` abre el tracker de la persona (`source_sheet`). Si el enriquecido lo
    sustituyera por el nombre con acentos, se estrenaría una partición vacía.
    """
    entrada = [{"name": "TERESA GARZA", "dept": "PRECIOS UNITARIOS", "type": "HIBRIDO"}]
    salida = enriquecer_directorio(entrada)[0]
    assert salida["name"] == "TERESA GARZA"
    assert salida["dept"] == "PRECIOS UNITARIOS"
    assert salida["type"] == "HIBRIDO"
    assert salida["nombre"] == "María Teresa Hernández Garza"
    assert salida["puesto"] == "Precios Unitarios"
    assert salida["foto"] == "/fotos/teresa-garza.jpg"


def test_quien_no_tiene_ficha_conserva_su_nombre_para_mostrar():
    salida = enriquecer_directorio([{"name": "DANIELA CASTRO", "dept": "GENERAL"}])[0]
    assert salida["nombre"] == "DANIELA CASTRO"
    assert salida["puesto"] == ""
    assert salida["foto"] == ""


def test_el_config_entrega_el_directorio_con_foto_y_puesto():
    from fastapi.testclient import TestClient

    from api.main import app

    datos = TestClient(app).get("/api/config", params={"role": "ADMIN", "username": "LUIS_CARLOS"}).json()
    directorio = {p["name"]: p for p in datos["directory"]}
    assert directorio["JAIME OLIVO"]["puesto"] == "Superintendente de construcción"
    assert directorio["JAIME OLIVO"]["foto"] == "/fotos/jaime-olivo.jpg"
    assert directorio["JAIME OLIVO"]["nombre"] == "Jaime Antonio Olivo Guerrero"
    # El enriquecido es aditivo: lo que ya traía la fila sigue ahí.
    assert directorio["JAIME OLIVO"]["dept"] == "CONSTRUCCION"
    assert "sales" in directorio["JAIME OLIVO"]


# --- Endpoint -----------------------------------------------------------
def test_el_endpoint_sirve_una_foto_del_catalogo():
    from fastapi.testclient import TestClient

    from api.main import app

    r = TestClient(app).get("/fotos/jaime-olivo.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content[:3] == b"\xff\xd8\xff"


@pytest.mark.parametrize(
    "archivo",
    [
        "main.py",                       # fuera del catálogo
        "../main.py",                    # travesía relativa
        "..%2F..%2Fapi%2Fmain.py",       # travesía codificada
        "",                              # ruta vacía
    ],
)
def test_el_endpoint_no_sirve_nada_que_no_este_en_el_catalogo(archivo):
    from fastapi.testclient import TestClient

    from api.main import app

    r = TestClient(app).get(f"/fotos/{archivo}")
    assert r.status_code == 404, f"/fotos/{archivo} respondió {r.status_code}"


# --- Vista --------------------------------------------------------------
def test_la_tarjeta_del_directorio_pinta_foto_nombre_y_puesto():
    """
    La comprobación es estática (como `test_api_contract.py`) porque la suite de
    Playwright se salta sola donde no hay navegador, y esta tarjeta es justo lo
    que el dueño pidió ver.
    """
    with open(INDEX_HTML, encoding="utf-8") as fh:
        html = fh.read()
    bloque = html[html.index('v-for="p in filteredStaff"'):]
    bloque = bloque[:bloque.index("</div>\n            </div>")]
    assert ':src="p.foto"' in bloque
    assert "{{p.nombre || p.name}}" in bloque
    assert "{{p.puesto}}" in bloque
    # Respaldo: sin foto (o con la foto rota) se sigue viendo la inicial.
    assert "staff-foto-inicial" in bloque
    assert "fotosRotas" in bloque
