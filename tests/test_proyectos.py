"""
Módulo de Proyectos / Cascada: `sites`, `projects` y las tareas etiquetadas.

Port de `apiSaveSite`, `apiSaveSubProject`, `apiFetchCascadeTree`,
`apiFetchProjectTasks` y `apiSaveProjectTask`.

La prueba con más valor de este archivo es
`test_fetch_project_tasks_no_replica_el_referenceerror_del_original`: en el
original esa función está rota al 100% de las llamadas y aquí se comprueba que
el port devuelve datos. Ver el docstring de `tracker_store.fetch_project_tasks`
para el detalle del fallo.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.repositories.proyectos import (  # noqa: E402
    ErrorDeLectura,
    RepositorioProyectos,
)


# --- Árbol de cascada -------------------------------------------------

def _engine_con_arbol():
    return MemoryEngine({
        "sites": [
            {"id_sitio": "SITE-1", "nombre": "PLANTA NORTE", "cliente": "ACME",
             "tipo": "CLIENTE", "estatus": "ACTIVO", "fecha_creacion": "2026-03-04",
             "creado_por": "LUIS_CARLOS"},
            {"id_sitio": "SITE-2", "nombre": "NAVE SUR", "cliente": "GLOBEX",
             "tipo": "CLIENTE", "estatus": "ACTIVO", "fecha_creacion": "",
             "creado_por": "LUIS_CARLOS"},
        ],
        "projects": [
            {"id_proyecto": "PROJ-1", "id_sitio": "SITE-1", "nombre_subproyecto": "PPC ELECTRICO",
             "tipo": "ELECTROMECANICA", "estatus": "ACTIVO"},
            {"id_proyecto": "PROJ-2", "id_sitio": "SITE-1", "nombre_subproyecto": "OBRA CIVIL",
             "tipo": "CONSTRUCCION", "estatus": "ACTIVO"},
            {"id_proyecto": "PROJ-3", "id_sitio": "SITE-404", "nombre_subproyecto": "HUERFANO",
             "tipo": "GENERAL", "estatus": "ACTIVO"},
        ],
    })


def test_arbol_agrupa_subproyectos_bajo_su_sitio():
    arbol = RepositorioProyectos(_engine_con_arbol()).arbol()

    assert [s["id"] for s in arbol] == ["SITE-1", "SITE-2"]
    norte = arbol[0]
    assert [p["name"] for p in norte["subProjects"]] == ["PPC ELECTRICO", "OBRA CIVIL"]
    assert arbol[1]["subProjects"] == []


def test_arbol_incluye_el_estado_que_espera_el_frontend():
    """La vista PROJECTS usa `expanded` y `subProjects` como estado del árbol."""
    sitio = RepositorioProyectos(_engine_con_arbol()).arbol()[0]
    assert sitio["expanded"] is False
    assert isinstance(sitio["subProjects"], list)
    assert sitio["client"] == "ACME"
    assert sitio["createdAt"] == "04/03/26 00:00"


def test_el_icono_depende_de_si_el_nombre_menciona_ppc():
    """Regla del original: los subproyectos PPC llevan otro icono."""
    subs = {p["name"]: p["icon"] for p in RepositorioProyectos(_engine_con_arbol()).arbol()[0]["subProjects"]}
    assert subs["PPC ELECTRICO"] == "fa-tasks"
    assert subs["OBRA CIVIL"] == "fa-clipboard-list"


def test_un_subproyecto_sin_sitio_padre_se_omite_sin_romper():
    """No se inventa un nodo raíz para un huérfano, pero tampoco se cae."""
    arbol = RepositorioProyectos(_engine_con_arbol()).arbol()
    nombres = [p["name"] for s in arbol for p in s["subProjects"]]
    assert "HUERFANO" not in nombres


def test_un_fallo_de_lectura_no_se_confunde_con_estar_vacio():
    class EngineRoto(MemoryEngine):
        def select(self, tabla, **kw):
            raise RuntimeError("red caída")

    with pytest.raises(ErrorDeLectura):
        RepositorioProyectos(EngineRoto()).arbol()


# --- Alta de sitios ---------------------------------------------------

def test_crear_sitio_normaliza_y_asigna_folio_site():
    engine = MemoryEngine({"sites": [], "projects": []})
    res = RepositorioProyectos(engine).crear_sitio("  planta norte ", "acme", None, "luis_carlos")

    assert res["success"] is True
    assert res["id"].startswith("SITE-")
    fila = engine.select("sites")[0]
    assert fila["nombre"] == "PLANTA NORTE"
    assert fila["cliente"] == "ACME"
    assert fila["tipo"] == "CLIENTE"      # respaldo del original
    assert fila["estatus"] == "ACTIVO"
    assert fila["creado_por"] == "LUIS_CARLOS"


def test_crear_sitio_rechaza_nombre_duplicado_sin_importar_formato():
    engine = MemoryEngine({"sites": [{"id_sitio": "SITE-1", "nombre": "PLANTA NORTE"}], "projects": []})
    res = RepositorioProyectos(engine).crear_sitio("planta norte", "otro")

    assert res["success"] is False
    assert "Ya existe" in res["message"]
    assert len(engine.select("sites")) == 1


def test_crear_sitio_exige_nombre():
    engine = MemoryEngine({"sites": [], "projects": []})
    assert RepositorioProyectos(engine).crear_sitio("   ", "acme")["success"] is False
    assert engine.select("sites") == []


# --- Alta de subproyectos --------------------------------------------

def test_crear_subproyecto_cuelga_del_sitio():
    engine = MemoryEngine({"sites": [{"id_sitio": "SITE-1", "nombre": "PLANTA NORTE"}], "projects": []})
    res = RepositorioProyectos(engine).crear_subproyecto("SITE-1", "obra civil", "CONSTRUCCION", "luis")

    assert res["success"] is True
    assert res["id"].startswith("PROJ-")
    fila = engine.select("projects")[0]
    assert fila["id_sitio"] == "SITE-1"
    assert fila["nombre_subproyecto"] == "OBRA CIVIL"


def test_el_nombre_de_subproyecto_solo_es_unico_dentro_de_su_sitio():
    """
    El mismo nombre en dos sitios distintos es válido: "OBRA CIVIL" puede
    existir en cada planta. La unicidad es del par (sitio, nombre).
    """
    engine = MemoryEngine({
        "sites": [{"id_sitio": "SITE-1"}, {"id_sitio": "SITE-2"}],
        "projects": [{"id_proyecto": "PROJ-1", "id_sitio": "SITE-1",
                      "nombre_subproyecto": "OBRA CIVIL"}],
    })
    repo = RepositorioProyectos(engine)

    assert repo.crear_subproyecto("SITE-1", "obra civil")["success"] is False
    repo.invalidar_caches()
    assert repo.crear_subproyecto("SITE-2", "obra civil")["success"] is True


def test_crear_subproyecto_exige_sitio():
    engine = MemoryEngine({"sites": [], "projects": []})
    res = RepositorioProyectos(engine).crear_subproyecto("", "obra civil")
    assert res["success"] is False
    assert "sitio" in res["message"].lower()


# --- Nombres de columna no verificables -------------------------------

def test_se_aceptan_nombres_de_columna_alternativos():
    """
    El esquema real no se puede introspeccionar desde el entorno de desarrollo,
    así que el repositorio resuelve la columna entre varios nombres plausibles.
    Si la base usara `id`/`name` en vez de `id_sitio`/`nombre`, debe funcionar
    igual en vez de devolver un árbol vacío.
    """
    engine = MemoryEngine({
        "sites": [{"id": "SITE-9", "name": "PLANTA X", "client": "ACME",
                   "type": "CLIENTE", "status": "ACTIVO"}],
        "projects": [{"id": "PROJ-9", "site_id": "SITE-9", "name": "SUB X",
                      "type": "GENERAL", "status": "ACTIVO"}],
    })
    arbol = RepositorioProyectos(engine).arbol()
    assert arbol[0]["name"] == "PLANTA X"
    assert [p["name"] for p in arbol[0]["subProjects"]] == ["SUB X"]


# --- Tareas de proyecto ----------------------------------------------

ENCABEZADOS = ["FOLIO", "CONCEPTO", "COMENTARIOS", "ESTATUS", "AVANCE"]


def _hoja_administrador():
    return [
        ENCABEZADOS,
        ["AD-0001", "Cambiar tablero", "urgente [PROY: PLANTA NORTE]", "PENDIENTE", "0"],
        ["AD-0002", "Pintar oficina", "sin proyecto", "PENDIENTE", "0"],
        ["AD-0003", "Revisar ductos [PROY: PLANTA NORTE]", "", "PENDIENTE", "50"],
        ["AD-0004", "Otra planta", "[PROY: NAVE SUR]", "PENDIENTE", "0"],
    ]


@pytest.fixture
def store_con_administrador(monkeypatch):
    from api.services import tracker_store

    monkeypatch.setattr(tracker_store, "read_values",
                        lambda nombre: _hoja_administrador() if nombre == "ADMINISTRADOR" else [])
    return tracker_store


def test_fetch_project_tasks_no_replica_el_referenceerror_del_original(store_con_administrador):
    """
    En el original esta función falla siempre: su última rama usa `sheetName`,
    que no existe en el ámbito (el parámetro es `projectName`), y el
    ReferenceError cae en el `catch`. Aquí tiene que devolver datos.
    """
    res = store_con_administrador.fetch_project_tasks("PLANTA NORTE")

    assert res["success"] is True, res.get("message")
    assert res["headers"] == ENCABEZADOS


def test_la_etiqueta_se_reconoce_en_concepto_y_en_comentarios(store_con_administrador):
    folios = [t["FOLIO"] for t in store_con_administrador.fetch_project_tasks("PLANTA NORTE")["data"]]
    # AD-0001 la trae en COMENTARIOS, AD-0003 en CONCEPTO.
    assert set(folios) == {"AD-0001", "AD-0003"}


def test_no_se_filtran_tareas_de_otro_proyecto_ni_sin_etiqueta(store_con_administrador):
    folios = [t["FOLIO"] for t in store_con_administrador.fetch_project_tasks("PLANTA NORTE")["data"]]
    assert "AD-0002" not in folios   # sin etiqueta
    assert "AD-0004" not in folios   # otro proyecto


def test_las_tareas_llegan_de_la_mas_reciente_a_la_mas_antigua(store_con_administrador):
    """`.reverse()` del original."""
    folios = [t["FOLIO"] for t in store_con_administrador.fetch_project_tasks("PLANTA NORTE")["data"]]
    assert folios == ["AD-0003", "AD-0001"]


def test_el_nombre_del_proyecto_es_insensible_a_mayusculas(store_con_administrador):
    a = store_con_administrador.fetch_project_tasks("planta norte")["data"]
    b = store_con_administrador.fetch_project_tasks("  PLANTA NORTE ")["data"]
    assert len(a) == len(b) == 2


def test_sin_nombre_de_proyecto_se_avisa(store_con_administrador):
    assert store_con_administrador.fetch_project_tasks("")["success"] is False


def test_save_project_task_agrega_la_etiqueta_una_sola_vez(monkeypatch):
    from api.services import tracker_store

    guardado = {}
    monkeypatch.setattr(tracker_store, "update_task",
                        lambda hoja, fila, usuario="": guardado.update(hoja=hoja, fila=fila, usuario=usuario)
                        or {"success": True, "data": fila})

    tracker_store.save_project_task({"FOLIO": "AD-1", "COMENTARIOS": "urgente"},
                                    "planta norte", "LUIS_CARLOS")
    assert guardado["hoja"] == "ADMINISTRADOR"
    assert guardado["fila"]["COMENTARIOS"] == "urgente [PROY: PLANTA NORTE]"

    # Segundo guardado de la misma fila: no debe duplicar la etiqueta.
    tracker_store.save_project_task(guardado["fila"], "planta norte", "LUIS_CARLOS")
    assert guardado["fila"]["COMENTARIOS"].count("[PROY: PLANTA NORTE]") == 1


def test_save_project_task_respeta_el_nombre_real_de_la_columna(monkeypatch):
    """
    Si la fila trae `Comentarios` en otra capitalización, se escribe en esa
    misma clave. Crear una nueva llamada `COMENTARIOS` dejaría el comentario
    original sin la etiqueta y añadiría una columna fantasma al guardar.
    """
    from api.services import tracker_store

    guardado = {}
    monkeypatch.setattr(tracker_store, "update_task",
                        lambda hoja, fila, usuario="": guardado.update(fila=fila)
                        or {"success": True, "data": fila})

    tracker_store.save_project_task({"FOLIO": "AD-1", "Comentarios": "algo"}, "NAVE SUR")
    assert "COMENTARIOS" not in guardado["fila"]
    assert guardado["fila"]["Comentarios"] == "algo [PROY: NAVE SUR]"
