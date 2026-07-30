"""
Borradores de PPC, agenda personal y hábitos.

Port de `apiFetchDrafts`, `apiSyncDrafts`, `apiClearDrafts`,
`apiSavePersonalEvent` y `apiSaveHabitLog`.

Las tres tablas comparten forma —registros sueltos con un dueño— y ninguna
tenía escritura en Python: los cinco métodos eran stubs. `ppc_borradores` (11
filas) y `personal_agenda` (27) ya existen en Supabase.

**`habits_log` es el caso distinto:** está mapeada en
`api/services/sheets.py:TABLAS_POR_HOJA` pero **no aparece en el inventario de
tablas reales** que documenta `scripts/verificar_base_tasks.py`. La lectura ya
tolera su ausencia (devuelve vacío con aviso); la escritura no puede, así que
falla con un mensaje que dice exactamente qué crear. El DDL está en
`docs/DDL_PENDIENTE.sql`. No se inventa la tabla desde el código.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from backend.core.engine import DataEngine

TABLA_BORRADORES = "ppc_borradores"
TABLA_AGENDA = "personal_agenda"
TABLA_HABITOS = "habits_log"

# Campo del frontend -> columna candidata. Igual que en `proyectos.py`, el
# esquema no se puede introspeccionar desde aquí, así que se resuelve contra las
# columnas que la base devuelva de verdad.
_CAMPOS_BORRADOR = {
    "especialidad": ("especialidad",),
    "concepto": ("concepto",),
    "responsable": ("responsable",),
    "horas": ("horas",),
    "cumplimiento": ("cumplimiento",),
    "archivoUrl": ("archivo", "archivo_url"),
    "comentarios": ("comentarios",),
    "comentariosPrevios": ("previos", "comentarios_previos"),
    "prioridades": ("prioridad", "prioridades"),
    "riesgos": ("riesgos",),
    "restricciones": ("restricciones",),
    "fechaRespuesta": ("fecha_resp", "fecha_respuesta"),
    "clasificacion": ("clasificacion",),
    "fechaAlta": ("fecha_alta",),
    "rutaCritica": ("ruta_critica",),
    "zona": ("zona",),
    "contratista": ("contratista",),
    "cuantReq": ("cuant_req",),
    "cuantReal": ("cuant_real",),
    "dias": ("dias_json",),
}

DIAS_VACIOS = {"l": False, "m": False, "x": False, "j": False, "v": False,
               "s": False, "d": False}


def _resolver(filas: Sequence[Dict[str, Any]], campos: Dict[str, tuple]) -> Dict[str, str]:
    presentes = set()
    for fila in filas or []:
        presentes.update(fila.keys())
    return {
        logico: next((c for c in candidatos if c in presentes), candidatos[0])
        for logico, candidatos in campos.items()
    }


class TablaAusente(RuntimeError):
    """La tabla no existe en el esquema. Distinto de estar vacía."""


class RepositorioBorradores:
    """
    Cola de captura de PPC. Es un borrador: se reemplaza entero, no se fusiona.

    El original hace `sheet.clear()` y reescribe todas las filas. Se conserva
    esa semántica porque el frontend manda siempre la lista completa: fusionar
    dejaría vivos los borradores que el usuario acaba de borrar.
    """

    def __init__(self, engine: DataEngine):
        self.engine = engine
        self._cols: Optional[Dict[str, str]] = None

    def cols(self) -> Dict[str, str]:
        if self._cols is None:
            self._cols = _resolver(self._leer(), _CAMPOS_BORRADOR)
        return self._cols

    def _leer(self) -> List[Dict[str, Any]]:
        try:
            return self.engine.select(TABLA_BORRADORES) or []
        except Exception as exc:  # noqa: BLE001
            raise TablaAusente(f"No se pudo leer `{TABLA_BORRADORES}`: {exc}") from exc

    def listar(self) -> List[Dict[str, Any]]:
        """Borradores en la forma que consume el frontend (claves camelCase)."""
        import json

        c = self.cols()
        salida = []
        for fila in self._leer():
            concepto = fila.get(c["concepto"])
            # El original descarta los que no tienen concepto: son filas vacías
            # que quedaron de una captura abandonada.
            if not str(concepto or "").strip():
                continue

            dias = dict(DIAS_VACIOS)
            crudo = fila.get(c["dias"])
            if crudo:
                try:
                    parsed = json.loads(crudo) if isinstance(crudo, str) else crudo
                    if isinstance(parsed, dict):
                        dias = parsed
                except (ValueError, TypeError):
                    # JSON corrupto: se cae a la semana vacía en vez de romper
                    # la carga de toda la cola, igual que el `try/catch` del
                    # original.
                    pass

            salida.append({
                logico: (dias if logico == "dias" else (fila.get(col) or ""))
                for logico, col in c.items()
            })
        return salida

    def reemplazar(self, borradores: Sequence[Dict[str, Any]]) -> int:
        """Borra todo y escribe la lista recibida. Devuelve cuántos quedaron."""
        import json

        c = self.cols()
        self.limpiar()
        if not borradores:
            return 0

        filas = []
        for d in borradores:
            fila = {}
            for logico, col in c.items():
                if logico == "dias":
                    fila[col] = json.dumps(d.get("dias") or {})
                elif logico == "cumplimiento":
                    # Respaldo del original: sin valor, 'NO'.
                    fila[col] = d.get("cumplimiento") or "NO"
                else:
                    fila[col] = d.get(logico) or ""
            filas.append(fila)

        self.engine.insertar(TABLA_BORRADORES, filas)
        return len(filas)

    def limpiar(self) -> None:
        """
        Vacía la tabla.

        `DataEngine.borrar` exige filtros —sin ellos lanza, a propósito, para
        que nadie borre una tabla entera por descuido—, así que se borra por la
        clave de cada fila existente.
        """
        c = self.cols()
        clave = c["concepto"]
        vistos = set()
        for fila in self._leer():
            valor = fila.get(clave)
            if valor is None or valor in vistos:
                continue
            vistos.add(valor)
            self.engine.borrar(TABLA_BORRADORES, {clave: valor})


class RepositorioAgenda:
    """Eventos personales y hábitos. Ambos son altas/actualizaciones por ID."""

    def __init__(self, engine: DataEngine):
        self.engine = engine

    def _existe(self, tabla: str) -> bool:
        try:
            self.engine.select(tabla, limite=1)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _guardar(self, tabla: str, fila: Dict[str, Any], prefijo: str) -> Dict[str, Any]:
        if not self._existe(tabla):
            raise TablaAusente(
                f"La tabla `{tabla}` no existe en la base. Créala con el DDL de "
                f"docs/DDL_PENDIENTE.sql y vuelve a intentarlo."
            )

        datos = {k: v for k, v in fila.items() if v is not None}
        # El original delega en `internalBatchUpdateTasks`, que resuelve la
        # identidad por ID; aquí se genera uno cuando falta para que un alta no
        # dependa de que el frontend lo invente.
        if not str(datos.get("id") or "").strip():
            datos["id"] = f"{prefijo}-{int(time.time() * 1000)}"

        self.engine.upsert(tabla, [datos], en_conflicto="id")
        return datos

    def guardar_evento(self, evento: Dict[str, Any], username: Any = "") -> Dict[str, Any]:
        fila = _claves_en_minuscula(evento)
        fila.setdefault("usuario_raw", str(username or "").strip())
        return self._guardar(TABLA_AGENDA, fila, "P")

    def guardar_habito(self, habito: Dict[str, Any], username: Any = "") -> Dict[str, Any]:
        fila = _claves_en_minuscula(habito)
        fila.setdefault("usuario_raw", str(username or "").strip())
        return self._guardar(TABLA_HABITOS, fila, "H")


def _claves_en_minuscula(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    El frontend manda las claves como encabezados de hoja (`TITULO`, `HORA_INICIO`)
    y las columnas de la base son minúsculas. `USUARIO` se traduce a
    `usuario_raw`, que es la columna real de las dos tablas.
    """
    fila = {}
    for clave, valor in (payload or {}).items():
        nombre = str(clave).strip().lower()
        if nombre in {"usuario", "user"}:
            nombre = "usuario_raw"
        if nombre.startswith("_"):
            continue  # `_rowIndex`, `_tempId`: estado del cliente
        fila[nombre] = valor
    return fila
