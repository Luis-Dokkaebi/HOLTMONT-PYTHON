#!/usr/bin/env python3
"""
Consolida las tareas duplicadas de `tasks`: una persona, una fila por folio.

El defecto que lo motivó (reportado por el dueño el 2026-08-14, con captura de
la tabla de Carlos Méndez): cada actividad aparecía dos veces en su tracker.

Causa medida en la base, no supuesta. Una persona tiene **dos** nombres —el de
su hoja (`staff_name`, "CARLOS MENDEZ") y el del directorio (`label`, "CARLOS
MENDEZ URBINA", que es lo que ofrece el selector de involucrados)— y el guardado
tomaba el segundo tal cual. Así nacía una segunda partición de la misma persona
con la fila copiada bajo otra identidad (`"CARLOS MENDEZ URBINA::PPC-544684601"`
en vez de `"PPC-544684601"`), invisible para la restricción única de
`dedupe_key`. La lectura sí une las dos particiones
(`organigrama.hojas_de_persona`), y de ahí el duplicado en pantalla.

El arreglo del código va en `api/services/asignacion.py`,
`api/services/organigrama.py` y `backend/repositories/tasks.py`
(`tests/test_duplicados_por_alias.py`). Este script limpia lo que ya se
escribió.

Qué borra, exactamente: filas que comparten **folio** con otra fila de la
**misma persona**. Nada más. Dos personas distintas con el mismo folio son la
difusión lateral ("papa caliente") y se conservan; dos filas de la misma persona
con folios distintos —aunque compartan CONCEPTO y FECHA— vienen de la hoja
original o de una importación, no de este defecto, y tampoco se tocan.

Qué conserva de cada grupo: la fila de la partición **canónica**, que es la que
abre el Tracker de esa persona (`organigrama.hoja_canonica`), y si el organigrama
no la conoce, la partición con más filas. Antes de borrar, la fila que se
conserva **hereda** de la copia todo dato que ella no tenga (columna vacía o
nula) y se queda con el mayor de los dos avances: consolidar no puede perder lo
que alguien capturó en la copia.

Uso:
    python scripts/deduplicar_tareas.py                 # simulación (por defecto)
    python scripts/deduplicar_tareas.py --aplicar       # escribe en la base
    python scripts/deduplicar_tareas.py --verificar     # solo comprueba que no queden

Requiere SUPABASE_URL y SUPABASE_KEY (lee `.env` de la raíz si existe). Antes de
escribir deja en `scripts/respaldos/duplicados_<marca>.json` las filas completas
que va a borrar, sus renglones de `task_involucrados` y los parches aplicados a
las que se conservan: es suficiente para revertir con un INSERT.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.core.engines.postgrest import PostgrestEngine  # noqa: E402
from backend.core.errors import ErrorDeMotor  # noqa: E402

TABLA = "tasks"
TABLA_HIJA = "task_involucrados"

# Columnas técnicas: no se heredan de la copia que se borra. `folio` y
# `concepto` tampoco, porque son la identidad de la tarea y ya coinciden.
NO_SE_HEREDAN = frozenset({"id", "dedupe_key", "source_sheet", "created_at",
                           "folio", "folio_sintetico"})

VERDE, ROJO, AMARILLO, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


# ----------------------------------------------------------------------
# Entorno
# ----------------------------------------------------------------------

def cargar_env() -> None:
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip())


# ----------------------------------------------------------------------
# Reglas puras (probadas en tests/test_deduplicar_tareas.py)
# ----------------------------------------------------------------------

def clave_hoja(nombre: Any) -> str:
    """Nombre de partición normalizado **solo para comparar**."""
    return " ".join(str(nombre or "").replace("_", " ").split()).upper()


def _vacio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


class _Conjuntos:
    """Union-find sobre nombres de partición. Lo mínimo para agruparlas."""

    def __init__(self, elementos: Sequence[str]):
        self._padre = {e: e for e in elementos}

    def raiz(self, x: str) -> str:
        while self._padre[x] != x:
            x = self._padre[x]
        return x

    def unir(self, a: str, b: str) -> None:
        ra, rb = self.raiz(a), self.raiz(b)
        if ra != rb:
            self._padre[rb] = ra

    def representantes(self) -> Dict[str, str]:
        return {e: self.raiz(e) for e in self._padre}


def _es_variante_de_grafia(a: str, b: str) -> bool:
    """
    ¿Son la misma hoja escrita de dos formas por la migración?

    Solo cuenta el prefijo, que es la forma exacta de los dos casos medidos:
    `…AVALOS` / `…AVALOS2` y `…COVARRUBIA` / `…COVARRUBIAS`. Compartir el
    nombre de pila no basta: 'ROCIO CASTRO' y 'ROCIO ABIGAIL CASTRO
    COVARRUBIA' son dos hojas distintas y unirlas sería decidir por parecido
    que dos personas son una.
    """
    ca, cb = clave_hoja(a), clave_hoja(b)
    return bool(ca) and bool(cb) and (ca.startswith(cb) or cb.startswith(ca))


def agrupar_particiones(hojas: Iterable[str],
                        alias: Optional[Mapping[str, Sequence[str]]] = None) -> Dict[str, str]:
    """
    Partición -> partición representante de la persona a la que pertenece.

    Dos particiones son de la misma persona cuando el organigrama lo dice
    (`alias`, que trae `hojas_de_persona`) o cuando una es una variante de
    grafía de la otra (ver `_es_variante_de_grafia`).
    """
    lista = sorted({str(h) for h in hojas})
    conjuntos = _Conjuntos(lista)
    _unir_por_alias(conjuntos, lista, alias or {})
    _unir_por_grafia(conjuntos, lista)
    return conjuntos.representantes()


def _unir_por_alias(conjuntos: "_Conjuntos", hojas: Sequence[str],
                    alias: Mapping[str, Sequence[str]]) -> None:
    """Une las particiones que el organigrama declara de la misma persona."""
    por_clave: Dict[str, List[str]] = collections.defaultdict(list)
    for hoja in hojas:
        por_clave[clave_hoja(hoja)].append(hoja)

    for nombre, equivalentes in alias.items():
        propias = por_clave.get(clave_hoja(nombre), [])
        equivalentes_reales = [b for e in equivalentes
                               for b in por_clave.get(clave_hoja(e), [])]
        for a in propias:
            for b in equivalentes_reales:
                conjuntos.unir(a, b)


def _unir_por_grafia(conjuntos: "_Conjuntos", hojas: Sequence[str]) -> None:
    """Une las dos grafías de una misma hoja que dejó la migración."""
    for i, a in enumerate(hojas):
        for b in hojas[i + 1:]:
            if _es_variante_de_grafia(a, b):
                conjuntos.unir(a, b)


def elegir_canonica(particiones: Sequence[str], conteos: Dict[str, int],
                    canonica_organigrama: str = "") -> str:
    """
    Partición que se conserva: la que abre el Tracker de la persona.

    El organigrama manda —es la que la persona ve— y solo cuenta si de verdad
    tiene filas en este grupo. Si no la conoce, gana la partición con más filas,
    y a igualdad el nombre por orden alfabético para que el resultado no dependa
    del orden de lectura.
    """
    claves = {clave_hoja(p): p for p in particiones}
    if canonica_organigrama and clave_hoja(canonica_organigrama) in claves:
        return claves[clave_hoja(canonica_organigrama)]
    return max(sorted(particiones), key=lambda p: conteos.get(p, 0))


def parche_de_herencia(conservada: Dict[str, Any],
                       borradas: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Lo que la fila conservada tiene que aprender de las copias antes de borrarlas.

    Dos reglas y ninguna más:

    * una columna vacía o nula en la conservada toma el primer valor no vacío
      que traiga una copia (así no se pierde el RELOJ, el archivo subido ni el
      comentario que se capturó en la copia);
    * `avance` se queda con el máximo. Es la única columna donde "lo que ya
      había" no basta: si alguien reportó 100 % en la copia, consolidar no puede
      devolver la tarea al 0 %.

    Nunca sobrescribe un valor que la conservada ya tenga: la fila que la persona
    ve es la que manda.

    Y no hereda un valor que sea **el nombre de la partición que se borra**. Las
    36 copias de César traen `assignee_raw` = "CESAR EDUARDO GARCIA AVALOS2":
    eso no es un dato que alguien capturó, es el nombre de la hoja repetida que
    estamos eliminando, y copiarlo dejaría ese "2" a la vista en la columna
    RESPONSABLE de una tarea que sí es suya.
    """
    parche: Dict[str, Any] = {}
    for copia in borradas:
        for columna, valor in _heredables(copia).items():
            if _vacio(conservada.get(columna)) and columna not in parche:
                parche[columna] = valor

    mayor = _mayor_avance(borradas)
    actual = conservada.get("avance")
    if mayor is not None and (actual is None or mayor > actual):
        parche["avance"] = mayor
    return parche


def _heredables(copia: Dict[str, Any]) -> Dict[str, Any]:
    """Columnas de una copia que pueden pasar a la fila que se conserva."""
    hoja = clave_hoja(copia.get("source_sheet"))
    return {
        columna: valor
        for columna, valor in copia.items()
        if columna not in NO_SE_HEREDAN
        and columna != "avance"          # tiene su propia regla: el máximo
        and not _vacio(valor)
        and clave_hoja(valor) != hoja    # no es un dato, es el nombre de la hoja
    }


def _mayor_avance(filas: Sequence[Dict[str, Any]]) -> Optional[float]:
    avances = [float(f["avance"]) for f in filas if f.get("avance") is not None]
    return max(avances) if avances else None


def plan_de_consolidacion(
    filas: Sequence[Dict[str, Any]],
    representante: Dict[str, str],
    canonicas: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Un grupo por (persona, folio) con más de una fila: qué se conserva y qué se borra.

    Devuelve decisiones ordenadas y explícitas —no ids sueltos— para que la
    simulación imprima exactamente lo que la escritura va a hacer.
    """
    conteos = collections.Counter(str(f.get("source_sheet") or "") for f in filas)
    grupos = _grupos_por_persona_y_folio(filas, representante)
    return [
        _decidir(persona, folio, copias, conteos, (canonicas or {}).get(persona, ""))
        for (persona, folio), copias in sorted(grupos.items())
        if len(copias) > 1
    ]


def _grupos_por_persona_y_folio(
    filas: Sequence[Dict[str, Any]], representante: Dict[str, str]
) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """Las filas agrupadas por (persona, folio). Sin folio no hay grupo posible."""
    grupos: Dict[Tuple[str, str], List[Dict[str, Any]]] = collections.defaultdict(list)
    for fila in filas:
        hoja = str(fila.get("source_sheet") or "")
        folio = str(fila.get("folio") or "").strip().upper()
        if folio:
            grupos[(representante.get(hoja, hoja), folio)].append(fila)
    return grupos


def _decidir(persona: str, folio: str, copias: Sequence[Dict[str, Any]],
             conteos: Dict[str, int], canonica_organigrama: str) -> Dict[str, Any]:
    """Qué se conserva y qué se borra de un grupo con más de una fila."""
    particiones = [str(c.get("source_sheet") or "") for c in copias]
    canonica = elegir_canonica(particiones, conteos, canonica_organigrama)
    en_canonica = [c for c in copias
                   if clave_hoja(c.get("source_sheet")) == clave_hoja(canonica)]

    if len(en_canonica) != 1:
        # Dos filas del mismo folio en la **misma** partición no las produce este
        # defecto (la clave única lo impide) y elegir cuál sobra sería inventar.
        return {"persona": persona, "folio": folio, "conservar": None, "borrar": [],
                "parche": {},
                "aviso": f"{len(en_canonica)} filas en la partición canónica "
                         f"{canonica!r}: se deja intacto"}

    conservada = en_canonica[0]
    borradas = [c for c in copias if c["id"] != conservada["id"]]
    return {"persona": persona, "folio": folio, "conservar": conservada,
            "borrar": borradas,
            "parche": parche_de_herencia(conservada, borradas), "aviso": ""}


# ----------------------------------------------------------------------
# Base de datos
# ----------------------------------------------------------------------

def alias_del_organigrama(hojas: Iterable[str]) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """Equivalencias y hoja canónica que declara el organigrama para cada partición."""
    from api.services import organigrama

    alias: Dict[str, List[str]] = {}
    canonica: Dict[str, str] = {}
    for hoja in hojas:
        equivalentes = organigrama.hojas_de_persona(hoja)
        if equivalentes:
            alias[hoja] = list(equivalentes)
            canonica[hoja] = equivalentes[0]
    return alias, canonica


def respaldar(plan: Sequence[Dict[str, Any]], involucrados: Dict[str, List[Dict[str, Any]]]) -> pathlib.Path:
    carpeta = RAIZ / "scripts" / "respaldos"
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ruta = carpeta / f"duplicados_{marca}.json"
    ruta.write_text(json.dumps(
        [
            {
                "persona": d["persona"],
                "folio": d["folio"],
                "conservada_id": (d["conservar"] or {}).get("id"),
                "parche": d["parche"],
                "borradas": d["borrar"],
                "task_involucrados": [r for f in d["borrar"]
                                      for r in involucrados.get(f["id"], [])],
            }
            for d in plan if d["conservar"]
        ],
        default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def aplicar(engine: PostgrestEngine, plan: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """
    Escribe: primero los parches, luego los hijos, luego las filas.

    El orden importa. Si el parche fuera después del borrado y el borrado
    fallara, la fila conservada se quedaría sin el dato que solo tenía la copia.
    Y `task_involucrados` va antes que `tasks` porque apunta a `tasks.id`: al
    revés, o la base rechaza el borrado por la clave ajena o quedan renglones
    huérfanos.
    """
    hechos = {"parches": 0, "involucrados": 0, "borradas": 0}
    for decision in plan:
        conservada = decision["conservar"]
        if not conservada:
            continue
        if decision["parche"]:
            # Las cuatro columnas NOT NULL sin DEFAULT viajan siempre, aunque no
            # cambien: un upsert de PostgREST es `INSERT ... ON CONFLICT DO
            # UPDATE`, y Postgres valida el NOT NULL sobre la tupla del INSERT
            # **antes** de resolver el conflicto. Mandar solo `{dedupe_key,
            # parche}` responde 400 con el código 23502; medido contra la base
            # el 2026-08-14 y ya documentado en
            # `TaskRepository._completar_obligatorias`.
            engine.upsert(TABLA, [{
                "dedupe_key": conservada["dedupe_key"],
                "folio": conservada.get("folio"),
                "concepto": conservada.get("concepto"),
                "source_sheet": conservada.get("source_sheet"),
                **decision["parche"],
            }], en_conflicto="dedupe_key")
            hechos["parches"] += 1
        for fila in decision["borrar"]:
            try:
                engine.borrar(TABLA_HIJA, {"task_id": fila["id"]})
                hechos["involucrados"] += 1
            except ErrorDeMotor as exc:
                print(f"  {AMARILLO}aviso{FIN}: {TABLA_HIJA} de {fila['id']}: {exc}")
            engine.borrar(TABLA, {"id": fila["id"]})
            hechos["borradas"] += 1
    return hechos


def duplicados_restantes(engine: PostgrestEngine) -> List[Dict[str, Any]]:
    """Relee la base y devuelve los grupos (persona, folio) que sigan con más de una fila."""
    filas = engine.select(TABLA, columnas=["id", "folio", "source_sheet", "dedupe_key", "concepto"])
    hojas = {str(f.get("source_sheet") or "") for f in filas}
    alias, canonica_por_hoja = alias_del_organigrama(hojas)
    representante = agrupar_particiones(hojas, alias)
    canonicas = {representante[h]: c for h, c in canonica_por_hoja.items() if h in representante}
    return [d for d in plan_de_consolidacion(filas, representante, canonicas) if d["borrar"]]


# ----------------------------------------------------------------------
# Informe
# ----------------------------------------------------------------------

def imprimir_plan(plan: Sequence[Dict[str, Any]]) -> None:
    por_persona: "collections.Counter[str]" = collections.Counter()
    for decision in plan:
        if decision["aviso"]:
            print(f"  {AMARILLO}AVISO{FIN} {decision['persona']} {decision['folio']}: "
                  f"{decision['aviso']}")
            continue
        por_persona[decision["persona"]] += len(decision["borrar"])
        conservada = decision["conservar"]
        borradas = ", ".join(f"{f['source_sheet']!r}" for f in decision["borrar"])
        parche = f"  hereda {sorted(decision['parche'])}" if decision["parche"] else ""
        print(f"  {decision['folio']:<22} conserva {conservada['source_sheet']!r:<36} "
              f"borra {borradas}{parche}")
    print()
    for persona, n in por_persona.most_common():
        print(f"  {n:>4} filas a borrar en {persona!r}")
    print(f"\n  total: {sum(por_persona.values())} filas")


def _verificar(engine: Any) -> int:
    """Modo `--verificar`: 0 si la base está limpia, 1 si queda algún duplicado."""
    restantes = duplicados_restantes(engine)
    if not restantes:
        print(f"{VERDE}Ninguna persona tiene tareas duplicadas.{FIN}")
        return 0
    print(f"{ROJO}Quedan {sum(len(d['borrar']) for d in restantes)} filas duplicadas "
          f"en {len(restantes)} grupos.{FIN}")
    imprimir_plan(restantes)
    return 1


def _planear(engine: Any) -> List[Dict[str, Any]]:
    """Lee la base entera y devuelve el plan de consolidación."""
    filas = engine.select(TABLA, columnas=["*"])
    hojas = {str(f.get("source_sheet") or "") for f in filas}
    alias, canonica_por_hoja = alias_del_organigrama(hojas)
    representante = agrupar_particiones(hojas, alias)
    canonicas = {representante[h]: c
                 for h, c in canonica_por_hoja.items() if h in representante}
    print(f"{len(filas)} filas en `{TABLA}`, {len(hojas)} particiones.\n")
    return plan_de_consolidacion(filas, representante, canonicas)


def _involucrados_de(engine: Any, plan: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Renglones de `task_involucrados` de las filas que se van a borrar."""
    por_tarea: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    ids = [f["id"] for d in plan for f in d["borrar"]]
    if not ids:
        return por_tarea
    for renglon in engine.select(TABLA_HIJA, columnas=["*"], donde_en={"task_id": ids}):
        por_tarea[str(renglon.get("task_id"))].append(renglon)
    return por_tarea


def _consolidar(engine: Any, plan: Sequence[Dict[str, Any]]) -> int:
    """Modo `--aplicar`: respalda, escribe y vuelve a verificar contra la base."""
    ruta = respaldar(plan, _involucrados_de(engine, plan))
    print(f"\nRespaldo en {ruta}")
    hechos = aplicar(engine, plan)
    print(f"{VERDE}Consolidado{FIN}: {hechos['borradas']} filas borradas, "
          f"{hechos['parches']} filas actualizadas con lo que traía la copia, "
          f"{hechos['involucrados']} borrados en `{TABLA_HIJA}`.")

    restantes = duplicados_restantes(engine)
    if restantes:
        print(f"{ROJO}Todavía quedan duplicados:{FIN}")
        imprimir_plan(restantes)
        return 1
    print(f"{VERDE}Verificado contra la base: ninguna persona tiene tareas duplicadas.{FIN}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true",
                        help="escribe en la base (por defecto solo simula)")
    parser.add_argument("--verificar", action="store_true",
                        help="solo comprueba que no queden duplicados y sale")
    args = parser.parse_args()

    cargar_env()
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Faltan SUPABASE_URL y SUPABASE_KEY (ver .env.example).", file=sys.stderr)
        return 2
    engine = PostgrestEngine(url, key)

    if args.verificar:
        return _verificar(engine)

    plan = _planear(engine)
    if not any(d["borrar"] for d in plan):
        print(f"{VERDE}No hay tareas duplicadas: nada que hacer.{FIN}")
        return 0
    imprimir_plan(plan)

    if not args.aplicar:
        print(f"\n{AMARILLO}Simulación: no se escribió nada.{FIN} "
              f"Repite con --aplicar para consolidar.")
        return 0
    return _consolidar(engine, plan)


if __name__ == "__main__":
    raise SystemExit(main())
