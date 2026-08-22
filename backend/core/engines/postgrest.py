"""
Motor sobre PostgREST (la API REST de Supabase).

Es la ruta que funciona sin TCP al 5432. Se usa `urllib` de la biblioteca
estándar en vez del cliente `supabase`, por dos razones concretas:

  * respeta `HTTPS_PROXY` y `SSL_CERT_FILE` del entorno sin configuración extra,
    que es lo que hace falta detrás del proxy de este despliegue;
  * `api/services/supabase_manager.py` **se traga todas las excepciones y
    devuelve `[]`**, de modo que un error de permisos y una tabla vacía son
    indistinguibles. Aquí un fallo levanta `ErrorDeMotor`.

Diferencia deliberada con `supabase_manager`: este módulo **no** convierte a
texto. Los tipos que entrega PostgREST (int, float, bool, None) llegan intactos
al repositorio, que es de lo que depende toda la Fase 1.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence

from backend.core.errors import ErrorDeMotor

PAGINA = 1000
TIEMPO_ESPERA = 30


class PostgrestEngine:
    """Implementación de `DataEngine` contra `/rest/v1`."""

    nombre = "postgrest"
    # PostgREST no expone BEGIN/COMMIT. Un `POST` con un arreglo de filas sí es
    # una sola sentencia y por tanto atómico; varias tablas en un mismo flujo
    # no lo son. El repositorio de tareas está escrito para no necesitarlo.
    soporta_transacciones = False
    # PostgREST no expone un canal para SQL arbitrario. Se declara en vez de
    # dejar que `consulta_cruda` lance: quien pregunta si puede, tiene que poder
    # saberlo SIN llamarla.
    soporta_sql_crudo = False

    def __init__(self, url: str, key: str, tiempo_espera: int = TIEMPO_ESPERA):
        self.base = url.rstrip("/") + "/rest/v1"
        self._key = key
        self.tiempo_espera = tiempo_espera

    # --- transporte ----------------------------------------------------

    def _cabeceras(self, prefer: str = "") -> Dict[str, str]:
        cabeceras = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            cabeceras["Prefer"] = prefer
        return cabeceras

    def _pedir(self, metodo: str, ruta: str, cuerpo: Any = None, prefer: str = "") -> Any:
        datos = None if cuerpo is None else json.dumps(cuerpo, default=str).encode("utf-8")
        peticion = urllib.request.Request(
            f"{self.base}/{ruta}", data=datos, headers=self._cabeceras(prefer), method=metodo
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.tiempo_espera) as respuesta:
                crudo = respuesta.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", "replace")[:500]
            # 23502 = not_null_violation. Es el error con el que ya tropezó la
            # normalización de estatus al escribir nulo en `tasks.status`.
            codigo = ""
            try:
                codigo = str(json.loads(detalle).get("code") or "")
            except (ValueError, AttributeError):
                pass
            raise ErrorDeMotor(
                f"PostgREST {metodo} {ruta} respondió {exc.code}",
                codigo=codigo,
                detalle=detalle,
                estado=int(exc.code),
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ErrorDeMotor(f"Fallo de red hacia PostgREST: {exc}") from exc

        if not crudo:
            return []
        try:
            return json.loads(crudo)
        except ValueError as exc:
            raise ErrorDeMotor(f"Respuesta no es JSON: {crudo[:200]}") from exc

    # --- operaciones ---------------------------------------------------

    def select(
        self,
        tabla: str,
        *,
        columnas: Optional[Sequence[str]] = None,
        donde: Optional[Dict[str, Any]] = None,
        donde_en: Optional[Dict[str, Sequence[Any]]] = None,
        orden: Optional[str] = None,
        limite: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        parametros: List[tuple] = [("select", ",".join(columnas) if columnas else "*")]
        for col, val in (donde or {}).items():
            parametros.append((col, f"eq.{val}"))
        for col, valores in (donde_en or {}).items():
            lista = ",".join(f'"{str(v)}"' for v in valores)
            parametros.append((col, f"in.({lista})"))
        if orden:
            parametros.append(("order", orden))

        filas: List[Dict[str, Any]] = []
        desplazamiento = 0
        while True:
            restante = PAGINA if limite is None else min(PAGINA, limite - len(filas))
            if restante <= 0:
                break
            consulta = list(parametros) + [
                ("offset", str(desplazamiento)),
                ("limit", str(restante)),
            ]
            pagina = self._pedir("GET", f"{tabla}?{urllib.parse.urlencode(consulta)}")
            if not isinstance(pagina, list):
                raise ErrorDeMotor(f"Se esperaba una lista de {tabla}, llegó {type(pagina).__name__}")
            filas.extend(pagina)
            if len(pagina) < restante:
                break
            desplazamiento += len(pagina)
        return filas

    def upsert(
        self,
        tabla: str,
        filas: Sequence[Dict[str, Any]],
        *,
        en_conflicto: str,
    ) -> List[Dict[str, Any]]:
        """
        Un solo `POST` con todas las filas: es una sentencia y por tanto atómica.

        `resolution=merge-duplicates` conserva en la base las columnas que no
        se envían, en vez de sobrescribirlas con nulo. Es la misma semántica
        que usa `SupabaseSync.mirrorBatch` en `CODIGO.js`.
        """
        if not filas:
            return []
        ruta = f"{tabla}?on_conflict={urllib.parse.quote(en_conflicto)}"
        resultado = self._pedir(
            "POST", ruta, list(filas), prefer="resolution=merge-duplicates,return=representation"
        )
        return resultado if isinstance(resultado, list) else []

    def insertar(self, tabla: str, filas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """INSERT puro: un conflicto de clave es un error, no una fusión."""
        if not filas:
            return []
        resultado = self._pedir("POST", tabla, list(filas), prefer="return=representation")
        return resultado if isinstance(resultado, list) else []

    def borrar(self, tabla: str, donde: Dict[str, Any]) -> None:
        """
        DELETE acotado por igualdad.

        Sin filtros PostgREST borraría la tabla entera, así que aquí eso es un
        error de programación y se detiene antes de salir a la red.
        """
        if not donde:
            raise ErrorDeMotor(f"DELETE sobre {tabla} sin filtros: se aborta por seguridad")
        consulta = urllib.parse.urlencode([(col, f"eq.{val}") for col, val in donde.items()])
        self._pedir("DELETE", f"{tabla}?{consulta}")

    @contextmanager
    def transaccion(self) -> Iterator["PostgrestEngine"]:
        """
        No hay transacción: PostgREST no la expone. El contexto existe para que
        el repositorio se escriba igual con ambos motores, pero no promete
        atomicidad más allá de la de cada sentencia. No se traga excepciones.
        """
        yield self

    # --- introspección --------------------------------------------------

    def esquema_openapi(self) -> Dict[str, Any]:
        """
        Definición del esquema que PostgREST publica en la raíz de `/rest/v1`.

        Es la forma de leer columnas, tipos y obligatoriedad **sin** TCP al
        5432, que es lo que permite verificar el esquema real desde este
        entorno en vez de asumirlo.
        """
        peticion = urllib.request.Request(
            self.base + "/", headers=self._cabeceras(), method="GET"
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.tiempo_espera) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ErrorDeMotor(f"No se pudo leer el esquema de PostgREST: {exc}") from exc

    def consulta_cruda(self, sql: str, *, tiempo_maximo_ms: int = 8000) -> List[Dict[str, Any]]:
        """
        No existe: PostgREST no expone un canal para SQL arbitrario.

        Se declara igual —y falla con un mensaje que dice qué hacer— porque la
        alternativa es que `api/services/agente_sql.py` reciba un `AttributeError`
        y el usuario vea "El agente no pudo completar la consulta" sin saber que
        lo que falta es una variable de entorno.
        """
        raise ErrorDeMotor(
            "El motor PostgREST no puede ejecutar SQL directo: el agente de "
            "consultas necesita DATABASE_URL (motor sqlalchemy)."
        )
