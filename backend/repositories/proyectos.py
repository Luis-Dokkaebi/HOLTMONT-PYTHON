"""
Repositorio de `sites` y `projects`: el módulo de Proyectos / Cascada.

Port de `apiSaveSite`, `apiSaveSubProject` y `apiFetchCascadeTree` de
`CODIGO.js`. Las tablas ya existen en Supabase (1 sitio y 4 proyectos al
migrar), pero no había endpoint que las leyera ni escribiera: el frontend tiene
las vistas PROJECTS y PROJECT_TASKS_VIEW y recibía listas vacías.

**Por qué los nombres de columna se resuelven y no se declaran.** Desde el
entorno de desarrollo no hay TCP al 5432 ni credenciales para introspeccionar el
esquema, así que declarar `id_sitio TEXT` sería una autoridad falsa — el mismo
razonamiento que `backend/models/__init__.py` documenta para no escribir los
modelos a mano. En su lugar se acepta un conjunto de nombres plausibles por
campo lógico (`_CAMPOS_SITIO`) y se resuelve contra las columnas que la base
devuelve de verdad, igual que `build_header_map` hace con las hojas. Cuando el
esquema se versione (`migration/schema.sql`), esto se puede simplificar a un
mapa fijo.
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Sequence

from backend.core.engine import DataEngine

TABLA_SITIOS = "sites"
TABLA_PROYECTOS = "projects"

# Campo lógico -> nombres aceptados, en orden de preferencia. El primero que
# exista entre las columnas reales gana.
_CAMPOS_SITIO = {
    "id": ("id_sitio", "site_id", "id"),
    "name": ("nombre", "nombre_sitio", "name"),
    "client": ("cliente", "client"),
    "type": ("tipo", "type"),
    "status": ("estatus", "status"),
    "created_at": ("fecha_creacion", "created_at", "creado_en"),
    "created_by": ("creado_por", "created_by"),
}

_CAMPOS_PROYECTO = {
    "id": ("id_proyecto", "project_id", "id"),
    "parent_id": ("id_sitio", "site_id", "parent_id", "id_padre"),
    "name": ("nombre_subproyecto", "nombre", "name"),
    "type": ("tipo", "especialidad", "type"),
    "status": ("estatus", "status"),
    "created_at": ("fecha_creacion", "created_at", "creado_en"),
    "created_by": ("creado_por", "created_by"),
}


def _norm(valor: Any) -> str:
    return str(valor or "").strip().upper()


class RepositorioProyectos:
    """Sitios y sus subproyectos. Un sitio es la raíz; un proyecto cuelga de él."""

    def __init__(self, engine: DataEngine):
        self.engine = engine
        self._cols_sitio: Optional[Dict[str, str]] = None
        self._cols_proyecto: Optional[Dict[str, str]] = None

    # --- Resolución de columnas ---------------------------------------

    def _resolver(self, filas: Sequence[Dict[str, Any]], campos: Dict[str, tuple]) -> Dict[str, str]:
        """
        Campo lógico -> columna real. Solo incluye los que existen.

        Con la tabla vacía no hay filas de las que deducir columnas; en ese caso
        se toma el primer nombre candidato de cada campo, que es el del esquema
        documentado en `docs/ARQUITECTURA_Y_BASE_DE_DATOS.md`. Insertar es
        entonces posible; si el nombre no fuera el correcto, la base rechaza el
        INSERT y el error sube — que es preferible a un guardado silencioso.
        """
        presentes = set()
        for fila in filas or []:
            presentes.update(fila.keys())

        resuelto = {}
        for logico, candidatos in campos.items():
            elegido = next((c for c in candidatos if c in presentes), None)
            resuelto[logico] = elegido or candidatos[0]
        return resuelto

    def cols_sitio(self) -> Dict[str, str]:
        if self._cols_sitio is None:
            self._cols_sitio = self._resolver(self._leer(TABLA_SITIOS), _CAMPOS_SITIO)
        return self._cols_sitio

    def cols_proyecto(self) -> Dict[str, str]:
        if self._cols_proyecto is None:
            self._cols_proyecto = self._resolver(self._leer(TABLA_PROYECTOS), _CAMPOS_PROYECTO)
        return self._cols_proyecto

    def _leer(self, tabla: str) -> List[Dict[str, Any]]:
        try:
            return self.engine.select(tabla) or []
        except Exception as exc:  # noqa: BLE001
            # Se distingue de "no hay datos": el llamador convierte esto en un
            # error visible en vez de una vista vacía, que es el fallo silencioso
            # que la Fase 0 del plan se dedicó a erradicar.
            raise ErrorDeLectura(f"No se pudo leer `{tabla}`: {exc}") from exc

    def invalidar_caches(self) -> None:
        self._cols_sitio = None
        self._cols_proyecto = None

    # --- Lectura -----------------------------------------------------

    def arbol(self) -> List[Dict[str, Any]]:
        """
        Árbol sitios -> subproyectos, en la forma que espera el frontend.

        Incluye `subProjects` y `expanded` porque la vista PROJECTS los usa como
        estado local del árbol desplegable, igual que en el original.
        """
        cs = self.cols_sitio()
        sitios = []
        indice = {}
        for fila in self._leer(TABLA_SITIOS):
            ident = str(fila.get(cs["id"]) or "").strip()
            if not ident:
                continue
            sitio = {
                "id": ident,
                "name": str(fila.get(cs["name"]) or "").strip(),
                "client": str(fila.get(cs["client"]) or ""),
                "type": str(fila.get(cs["type"]) or "CLIENTE"),
                "status": str(fila.get(cs["status"]) or "ACTIVO"),
                "createdAt": _fecha_corta(fila.get(cs["created_at"])),
                "subProjects": [],
                "expanded": False,
            }
            sitios.append(sitio)
            indice[ident] = sitio

        cp = self.cols_proyecto()
        for fila in self._leer(TABLA_PROYECTOS):
            padre = indice.get(str(fila.get(cp["parent_id"]) or "").strip())
            if padre is None:
                # Subproyecto huérfano: su sitio no existe. No se inventa un
                # nodo raíz; se omite y queda constancia en el log.
                print(f"[proyectos] Subproyecto sin sitio padre: {fila.get(cp['id'])}")
                continue
            nombre = str(fila.get(cp["name"]) or "").strip()
            padre["subProjects"].append({
                "id": fila.get(cp["id"]),
                "name": nombre,
                "type": str(fila.get(cp["type"]) or "GENERAL"),
                "status": str(fila.get(cp["status"]) or "ACTIVO"),
                # El original elige el icono por el nombre; se conserva.
                "icon": "fa-tasks" if "PPC" in nombre.upper() else "fa-clipboard-list",
            })

        return sitios

    # --- Escritura ---------------------------------------------------

    def crear_sitio(self, nombre: Any, cliente: Any, tipo: Any = None,
                    creado_por: Any = None) -> Dict[str, Any]:
        """
        Alta de sitio. Rechaza nombres duplicados, como el original.

        El original tomaba un `LockService` de 5 s para serializar la
        comprobación de duplicados con el alta. Aquí no hay candado equivalente:
        dos altas simultáneas del mismo nombre pueden colarse. Es la misma
        carrera que la Fase 2 del plan resuelve para los folios, y la solución
        definitiva es un índice UNIQUE sobre el nombre del sitio.
        """
        cs = self.cols_sitio()
        limpio = _norm(nombre)
        if not limpio:
            return {"success": False, "message": "El sitio necesita un nombre."}

        existentes = {_norm(f.get(cs["name"])) for f in self._leer(TABLA_SITIOS)}
        if limpio in existentes:
            return {"success": False, "message": "Ya existe un sitio con ese nombre."}

        ident = f"SITE-{int(time.time() * 1000)}"
        fila = {
            cs["id"]: ident,
            cs["name"]: limpio,
            cs["client"]: _norm(cliente),
            cs["type"]: tipo or "CLIENTE",
            cs["status"]: "ACTIVO",
            cs["created_by"]: _norm(creado_por) or "ANONIMO",
        }
        self.engine.insertar(TABLA_SITIOS, [fila])
        return {"success": True, "id": ident, "message": "Sitio creado correctamente."}

    def crear_subproyecto(self, id_sitio: Any, nombre: Any, tipo: Any = None,
                          creado_por: Any = None) -> Dict[str, Any]:
        """Alta de subproyecto. El par (sitio, nombre) debe ser único."""
        cp = self.cols_proyecto()
        limpio = _norm(nombre)
        padre = str(id_sitio or "").strip()
        if not limpio:
            return {"success": False, "message": "El subproyecto necesita un nombre."}
        if not padre:
            return {"success": False, "message": "Falta el sitio al que pertenece."}

        for fila in self._leer(TABLA_PROYECTOS):
            mismo_padre = str(fila.get(cp["parent_id"]) or "").strip() == padre
            if mismo_padre and _norm(fila.get(cp["name"])) == limpio:
                return {"success": False, "message": "Ya existe ese subproyecto en este sitio."}

        ident = f"PROJ-{int(time.time() * 1000)}-{random.randint(0, 999)}"
        fila = {
            cp["id"]: ident,
            cp["parent_id"]: padre,
            cp["name"]: limpio,
            cp["type"]: tipo or "GENERAL",
            cp["status"]: "ACTIVO",
            cp["created_by"]: _norm(creado_por) or "ANONIMO",
        }
        self.engine.insertar(TABLA_PROYECTOS, [fila])
        return {"success": True, "id": ident, "message": "Subproyecto agregado."}


class ErrorDeLectura(RuntimeError):
    """La tabla no se pudo leer. Distinto de que esté vacía."""


def _fecha_corta(valor: Any) -> str:
    """`dd/MM/yy HH:mm`, el formato que el original mandaba al frontend."""
    if not valor:
        return ""
    from api.services.tracker_rules import parse_sheet_date

    fecha = parse_sheet_date(valor)
    return fecha.strftime("%d/%m/%y %H:%M") if fecha else str(valor)
