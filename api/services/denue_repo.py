"""
El catálogo del DENUE: la única capa que sabe que hay un SQLite debajo.

Por qué existe este módulo
--------------------------
El módulo de prospección lee 20,957 establecimientos del INEGI que **no
cambian entre publicaciones del instituto** (semestrales). Hay tres formas de
servirlos y solo una cabe:

1. **Parquet + pandas en la API.** Descartada por peso: `pandas` (42 MB),
   `numpy` (58 MB) y `pyarrow` (152 MB) desempaquetadas suman **251 MB** y
   rebasan solas el límite de 250 MB de una función serverless de Vercel,
   antes de `fastapi`, `supabase`, `sqlalchemy` y `langchain`, que ya están.
2. **Tabla en Supabase.** Viable, pero paga red y carga inicial para leer un
   dato de terceros que nunca cambia, y mete 21,000 filas ajenas en los
   respaldos de la empresa.
3. **SQLite de solo lectura en el bundle.** 5.6 MB, consultas de 3 a 14 ms con
   el módulo `sqlite3` de la **biblioteca estándar**. Cero dependencias nuevas,
   cero infraestructura, arranque en frío plano.

Se eligió la tercera. Su costo real —"actualizar el dato exige desplegar"— es
irrelevante cuando el dato se publica cada semestre.

Este archivo aísla esa decisión. `api/services/prospeccion.py` recibe un
repositorio y no sabe si detrás hay un archivo, una tabla o un diccionario: por
eso las pruebas corren contra un SQLite de veinte filas en `tmp_path` y por eso
mover el catálogo a Supabase el día que crezca es cambiar una implementación,
no la vista.

El artefacto lo genera `scripts/construir_sqlite.py` del repositorio `ModeloGeo`
a partir de `denue_construccion.parquet`, y se copia aquí ya construido. `pandas`
y `pyarrow` se quedan en aquel repositorio: ese es el punto de todo el diseño.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# El artefacto viaja en el bundle, junto al código que lo lee.
RUTA_CATALOGO = Path(__file__).resolve().parent.parent / "data" / "denue.sqlite"

# Las 10 columnas que pinta el mapa y que forman la ficha del negocio. El SQLite
# tiene 14 y el DENUE 42: lo que sale por la API es este subconjunto y nada más.
# Una fila del DENUE completo son ~1.5 KB; 3,000 marcadores serían 4.5 MB de
# JSON por paneo del mapa.
COLUMNAS_DEL_MAPA = (
    "id", "nom_estab", "nombre_act", "per_ocu", "telefono",
    "correoelec", "www", "municipio", "latitud", "longitud",
)


class RepositorioDenue:
    """
    Lectura del catálogo. Abre en solo lectura y cachea la conexión.

    **Solo lectura de verdad** (`file:…?mode=ro`, `uri=True`): no es higiene,
    es la garantía de que ningún camino del código —ni un `INSERT` escrito por
    error, ni un futuro endpoint— pueda tocar un archivo que viaja en el bundle
    y que se regenera desde `ModeloGeo`. En modo `ro` SQLite ni siquiera crea el
    archivo si no existe, así que una ruta mal escrita falla al abrir en vez de
    devolver una base vacía con cero establecimientos.

    **Caché por hilo dentro del proceso.** Abrir el archivo cuesta poco pero no
    cero, y el arranque en frío de la función serverless es donde se nota. La
    caché es por hilo y no una sola conexión global porque FastAPI despacha los
    endpoints síncronos en un *threadpool*, y un objeto `Connection` de `sqlite3`
    no se comparte entre hilos. Cada hilo del pool abre la suya una vez y la
    reusa para todas las peticiones que atienda después.
    """

    def __init__(self, ruta: Path = RUTA_CATALOGO) -> None:
        self.ruta = Path(ruta)
        self._locales = threading.local()

    def conexion(self) -> sqlite3.Connection:
        """La conexión de este hilo, abriéndola la primera vez."""
        cacheada = getattr(self._locales, "conexion", None)
        if cacheada is None:
            cacheada = sqlite3.connect(f"file:{self.ruta}?mode=ro", uri=True)
            cacheada.row_factory = sqlite3.Row
            self._locales.conexion = cacheada
        return cacheada

    def consultar(self, sql: str, parametros: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        """
        Filas como diccionarios.

        `parametros` va siempre por marcador `?`. Los filtros de este módulo
        vienen de la barra de búsqueda del navegador: interpolarlos en el SQL
        sería inyección, y en una base de solo lectura seguiría permitiendo leer
        `sqlite_master` entero.
        """
        cursor = self.conexion().execute(sql, tuple(parametros))
        try:
            return [dict(fila) for fila in cursor.fetchall()]
        finally:
            cursor.close()

    def escalar(self, sql: str, parametros: Sequence[Any] = ()) -> Any:
        """El primer valor de la primera fila. Para los `COUNT(*)`."""
        cursor = self.conexion().execute(sql, tuple(parametros))
        try:
            fila = cursor.fetchone()
        finally:
            cursor.close()
        return None if fila is None else fila[0]

    def cerrar(self) -> None:
        """Cierra la conexión de este hilo. Las pruebas lo usan; el runtime no."""
        cacheada = getattr(self._locales, "conexion", None)
        if cacheada is not None:
            cacheada.close()
            self._locales.conexion = None


_repositorio: Optional[RepositorioDenue] = None


def repositorio_disponible(ruta: Optional[Path] = None) -> Optional[RepositorioDenue]:
    """
    El repositorio del catálogo, o `None` si el artefacto no está desplegado.

    Devolver `None` en vez de lanzar es el mismo criterio que
    `api.services.plano.llm_disponible()`: la falta de un artefacto opcional no
    puede tumbar el arranque de la API entera. El servicio traduce ese `None` a
    un `success: false` con un motivo accionable, y el resto de la plataforma
    sigue en pie.

    La ruta se resuelve **en cada llamada** y no como valor por defecto del
    parámetro: un default se congela al importar el módulo, y entonces apuntar el
    catálogo a otro archivo —lo que hacen las pruebas para no cargar los 5.6 MB
    del artefacto real— dejaría de funcionar sin que nadie lo note.

    La instancia se guarda a nivel de módulo —una por proceso— porque es la que
    sostiene la caché de conexiones.
    """
    global _repositorio
    destino = Path(ruta) if ruta is not None else Path(RUTA_CATALOGO)
    if not destino.is_file():
        return None
    if _repositorio is None or _repositorio.ruta != destino:
        _repositorio = RepositorioDenue(destino)
    return _repositorio
