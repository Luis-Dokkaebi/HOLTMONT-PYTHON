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


# Nombre de la función de solo lectura que el Agente de Consultas llama por RPC.
# La crea `docs/DDL_AGENTE_SQL.sql`. Es una constante y no una variable de
# entorno a propósito: el nombre lo fija ese archivo, y tener que mantenerlos
# sincronizados en dos sitios es una forma de romperlo sin enterarse.
FUNCION_AGENTE = "agente_sql_consulta"

# Códigos con los que **PostgREST** dice "esa función no está en mi caché de
# esquema". Son suyos, no de PostgreSQL, y por eso son inequívocos: si aparecen,
# la llamada RPC no llegó ni a ejecutarse.
CODIGOS_FUNCION_AUSENTE = frozenset({"PGRST202", "PGRST203"})

# `undefined_function` de PostgreSQL. Ambiguo a propósito: lo levanta tanto una
# función que el modelo se inventó dentro del SELECT como la nuestra si se
# borró. Se resuelve mirando de qué función habla el cuerpo del error, nunca el
# estado HTTP. Ver `_falta_la_funcion_del_agente`.
CODIGO_FUNCION_INDEFINIDA = "42883"


def _falta_la_funcion_del_agente(exc: ErrorDeMotor) -> bool:
    """
    Si el 404 significa "hay que ejecutar el DDL" y no "reescribe la consulta".

    **El estado HTTP no sirve para decidirlo, y creer que sí fue el bug.**
    PostgREST traduce a 404 tanto sus propios `PGRST202`/`PGRST203` como los
    `42P01` (tabla inexistente) y `42883` (función inexistente) que levanta
    PostgreSQL al ejecutar el SELECT de dentro —está en `pgErrorStatus`, en
    `PostgREST/Error.hs`—. Con la regla vieja (`exc.estado == 404`), un
    `relation "tasks" does not exist` salía por pantalla como «La función
    agente_sql_consulta no existe en la base. Ejecuta docs/DDL_AGENTE_SQL.sql»,
    con la función instalada y respondiendo. El usuario ejecutaba el archivo,
    no cambiaba nada, y no había pista de por dónde seguir.

    Los tres casos que sí son configuración:

    * `PGRST202`/`PGRST203`: PostgREST no encontró la función, o no supo elegir
      entre dos con el mismo nombre.
    * Un 404 **sin `code`**: no hubo cuerpo JSON que analizar, así que el que
      falta es el propio camino `/rest/v1/rpc/...`.
    * Un `42883` cuyo mensaje nombra a `agente_sql_consulta`: la función se
      borró después de que PostgREST cargara su caché.

    Todo lo demás es error de la consulta y vuelve tal cual, para que el bucle
    de auto-corrección se lo pueda enseñar al modelo.
    """
    if exc.codigo in CODIGOS_FUNCION_AUSENTE:
        return True
    if exc.estado != 404:
        return False
    if not exc.codigo:
        return True
    # Solo el cuerpo del error, nunca `str(exc)`: el texto lleva la ruta
    # `rpc/agente_sql_consulta` siempre, así que buscar ahí el nombre da
    # verdadero también cuando la función que falta es una que inventó el
    # modelo. Medido: la prueba de la función inventada pasaba a configuración.
    return (exc.codigo == CODIGO_FUNCION_INDEFINIDA
            and FUNCION_AGENTE in (exc.detalle or ""))


def _codigo_y_mensaje(detalle: str) -> tuple:
    """
    `(code, message)` del cuerpo de error de PostgREST; `("", "")` si no es JSON.

    Un cuerpo no-JSON no es excepcional: un 502 del balanceador o una página de
    error del proxy llegan como HTML. Por eso se devuelve el par vacío en vez de
    lanzar: el estado HTTP ya viaja aparte y sigue sirviendo.
    """
    try:
        cuerpo = json.loads(detalle)
    except (ValueError, TypeError):
        return "", ""
    if not isinstance(cuerpo, dict):
        return "", ""
    return str(cuerpo.get("code") or ""), str(cuerpo.get("message") or "")


class ErrorDeConfiguracion(ErrorDeMotor):
    """
    Falta algo por instalar o configurar; reescribir la consulta no lo arregla.

    Existe para que `api/services/agente_sql.py` NO reintente: es la diferencia
    entre gastar tres llamadas al modelo y decir de una vez qué hay que hacer.
    """


def _traducir_error_de_rpc(exc: ErrorDeMotor) -> ErrorDeMotor:
    """Convierte 'la función no existe' en un error accionable; el resto pasa igual."""
    if _falta_la_funcion_del_agente(exc):
        return ErrorDeConfiguracion(
            f"La función {FUNCION_AGENTE} no existe en la base. Ejecuta "
            "`docs/DDL_AGENTE_SQL.sql` en el SQL Editor de Supabase (una sola "
            "vez); no hace falta ninguna variable de entorno nueva.",
            codigo=exc.codigo, detalle=exc.detalle, estado=exc.estado)
    if exc.estado in (401, 403):
        return ErrorDeConfiguracion(
            f"La clave configurada no tiene permiso para ejecutar {FUNCION_AGENTE}. "
            "El DDL la concede solo a `service_role`: revisa que SUPABASE_KEY sea "
            "la clave de servicio y no la publicable.",
            codigo=exc.codigo, detalle=exc.detalle, estado=exc.estado)
    return exc


class PostgrestEngine:
    """Implementación de `DataEngine` contra `/rest/v1`."""

    nombre = "postgrest"
    # PostgREST no expone BEGIN/COMMIT. Un `POST` con un arreglo de filas sí es
    # una sola sentencia y por tanto atómico; varias tablas en un mismo flujo
    # no lo son. El repositorio de tareas está escrito para no necesitarlo.
    soporta_transacciones = False
    # Puede, pero solo a través de la función RPC de `docs/DDL_AGENTE_SQL.sql`.
    # Se declara `True` porque la capacidad existe; que la función esté instalada
    # o no es configuración del despliegue, y `consulta_cruda` lo dice con un
    # error que nombra el archivo a ejecutar.
    soporta_sql_crudo = True

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
            codigo, mensaje_db = _codigo_y_mensaje(detalle)
            # El `message` de PostgREST va en el texto, no solo en `detalle`.
            # Lo que llega a pantalla y al reintento del agente es `str(exc)`:
            # sin esto, un `relation "tasks" does not exist` se leía como
            # "PostgREST POST rpc/agente_sql_consulta respondió 404", que dice
            # que algo falló y nada de qué. Se añade al final para no romper a
            # quien busca "respondió 404" (`backend/routers/tickets.py`).
            resumen = f"PostgREST {metodo} {ruta} respondió {exc.code}"
            raise ErrorDeMotor(
                f"{resumen}: {mensaje_db}" if mensaje_db else resumen,
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
        Ejecuta un SELECT ya validado a través de la función RPC del agente.

        PostgREST no tiene un canal para SQL arbitrario, pero sí para llamar
        funciones. `docs/DDL_AGENTE_SQL.sql` crea una declarada `STABLE`, y de
        ahí sale la garantía de solo lectura que importa: PostgreSQL **prohíbe**
        modificar datos dentro de una función no volátil, y lo impone el
        ejecutor. El guardarraíl de texto de `agente_sql.validar_sql` sigue
        delante; esta es la capa que no depende de que un regex esté bien
        escrito.

        El tiempo máximo lo fija la propia función (`set local
        statement_timeout`), no esta llamada: viaja con la definición, así que no
        se puede saltar desde el cliente. `tiempo_maximo_ms` se acepta para
        cumplir el protocolo y se ignora a propósito.

        **Por qué existe, pudiendo conectar directo a Postgres.** Porque el
        despliegue usa PostgREST: `AGENTE_SQL_DATABASE_URL` es la alternativa y
        tiene prioridad, pero exige una credencial nueva. Este camino funciona
        con las `SUPABASE_URL`/`SUPABASE_KEY` que la aplicación ya tiene.
        """
        try:
            resultado = self._pedir(
                "POST", f"rpc/{FUNCION_AGENTE}", {"consulta": sql})
        except ErrorDeMotor as exc:
            raise _traducir_error_de_rpc(exc) from exc

        # La función devuelve `jsonb`: una lista de objetos, o `[]`.
        if resultado is None:
            return []
        if isinstance(resultado, list):
            return [f for f in resultado if isinstance(f, dict)]
        raise ErrorDeMotor(
            f"La función {FUNCION_AGENTE} devolvió {type(resultado).__name__}, "
            "se esperaba una lista.")
