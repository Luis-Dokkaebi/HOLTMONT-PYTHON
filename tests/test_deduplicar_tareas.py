"""
Pruebas de `scripts/deduplicar_tareas.py`.

Cada caso de aquí sale de una fila real de la base, no de una hipótesis. Los
tres grupos de particiones que se midieron el 2026-08-14 antes de escribir el
script:

    CARLOS MENDEZ (220 filas)                     / CARLOS MENDEZ URBINA (11)
    CESAR EDUARDO GARCIA AVALOS (147)             / …AVALOS2 (36)
    ROCIO ABIGAIL CASTRO COVARRUBIA (223)         / …COVARRUBIAS (24)

Los dos primeros vienen de los dos nombres de la persona (`staff_name` y
`label`); el tercero, de la grafía truncada que dejó la migración. En los tres
casos la fila que hay que conservar es la de la partición que **abre su
Tracker**, y esa la dice el organigrama: para Rocío es `…COVARRUBIAS`, la de 24
filas, aunque la otra tenga diez veces más. Elegir "la más grande" daría la
respuesta equivocada justo ahí, y por eso el organigrama gana sobre el conteo.

Lo que **no** se borra tiene tanta prueba como lo que sí: dos personas con el
mismo folio son difusión lateral, y dos folios distintos de la misma persona
—aunque compartan CONCEPTO y FECHA— vienen de la hoja original.
"""

from __future__ import annotations

import importlib.util
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _cargar_modulo():
    """El script vive en `scripts/`, que no es un paquete importable."""
    ruta = RAIZ / "scripts" / "deduplicar_tareas.py"
    spec = importlib.util.spec_from_file_location("deduplicar_tareas", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


dedup = _cargar_modulo()

CARLOS, CARLOS_LARGO = "CARLOS MENDEZ", "CARLOS MENDEZ URBINA"
ROCIO_CORTA = "ROCIO ABIGAIL CASTRO COVARRUBIA"
ROCIO_LARGA = "ROCIO ABIGAIL CASTRO COVARRUBIAS"


def fila(folio: str, hoja: str, **extra) -> dict:
    base = {
        "id": f"id-{hoja}-{folio}",
        "dedupe_key": folio if hoja == CARLOS else f"{hoja}::{folio}",
        "folio": folio,
        "source_sheet": hoja,
        "concepto": "REVISION DE CORREOS ELECTRONICOS",
        "fecha_alta": "2026-08-12",
        "avance": 0.0,
        "status": "ASIGNADO",
    }
    base.update(extra)
    return base


class TestAgruparParticiones:
    """Qué particiones son la misma persona."""

    def test_el_organigrama_une_los_dos_nombres_de_una_persona(self):
        rep = dedup.agrupar_particiones(
            [CARLOS, CARLOS_LARGO, "RICARDO MENDO"],
            {CARLOS: [CARLOS, CARLOS_LARGO]})
        assert rep[CARLOS] == rep[CARLOS_LARGO]
        assert rep["RICARDO MENDO"] != rep[CARLOS]

    def test_la_grafia_truncada_de_la_migracion_se_une_por_prefijo(self):
        """El organigrama no conoce `…COVARRUBIA` (sin S): la une el prefijo."""
        rep = dedup.agrupar_particiones([ROCIO_CORTA, ROCIO_LARGA])
        assert rep[ROCIO_CORTA] == rep[ROCIO_LARGA]

    def test_la_hoja_repetida_con_un_2_al_final_se_une(self):
        rep = dedup.agrupar_particiones(
            ["CESAR EDUARDO GARCIA AVALOS", "CESAR EDUARDO GARCIA AVALOS2"])
        assert len(set(rep.values())) == 1

    def test_dos_personas_que_comparten_el_nombre_de_pila_no_se_unen(self):
        """"ROCIO CASTRO" no es prefijo de "ROCIO ABIGAIL…": son dos hojas."""
        rep = dedup.agrupar_particiones(["ROCIO CASTRO", ROCIO_CORTA])
        assert rep["ROCIO CASTRO"] != rep[ROCIO_CORTA]

    def test_personas_distintas_quedan_separadas(self):
        hojas = ["JEHU MARTINEZ", "GERALDINE MARTINEZ HERNANDEZ", "SONIA GARCIA PEREZ"]
        assert len(set(dedup.agrupar_particiones(hojas).values())) == 3


class TestElegirCanonica:
    """La fila que se conserva es la que la persona ve."""

    def test_manda_el_organigrama_aunque_tenga_menos_filas(self):
        """El caso de Rocío: 24 filas ganan a 223 porque su vista abre esa."""
        elegida = dedup.elegir_canonica(
            [ROCIO_CORTA, ROCIO_LARGA],
            {ROCIO_CORTA: 223, ROCIO_LARGA: 24},
            canonica_organigrama=ROCIO_LARGA)
        assert elegida == ROCIO_LARGA

    def test_sin_organigrama_gana_la_particion_con_mas_filas(self):
        elegida = dedup.elegir_canonica(
            ["CESAR EDUARDO GARCIA AVALOS", "CESAR EDUARDO GARCIA AVALOS2"],
            {"CESAR EDUARDO GARCIA AVALOS": 147, "CESAR EDUARDO GARCIA AVALOS2": 36})
        assert elegida == "CESAR EDUARDO GARCIA AVALOS"

    def test_una_canonica_sin_filas_en_el_grupo_no_se_usa(self):
        """Si el organigrama nombra una hoja que no está en el grupo, se ignora."""
        elegida = dedup.elegir_canonica(
            [CARLOS_LARGO], {CARLOS_LARGO: 11}, canonica_organigrama=CARLOS)
        assert elegida == CARLOS_LARGO


class TestParcheDeHerencia:
    """Consolidar no puede perder lo que se capturó en la copia."""

    def test_la_columna_vacia_toma_el_valor_de_la_copia(self):
        parche = dedup.parche_de_herencia(
            fila("PPC-1", CARLOS, reloj=None, carpeta=""),
            [fila("PPC-1", CARLOS_LARGO, reloj="1", carpeta="http://drive/x")])
        assert parche["reloj"] == "1"
        assert parche["carpeta"] == "http://drive/x"

    def test_no_se_pisa_lo_que_la_conservada_ya_tiene(self):
        parche = dedup.parche_de_herencia(
            fila("PPC-1", CARLOS, comentarios="lo mío"),
            [fila("PPC-1", CARLOS_LARGO, comentarios="Asignada desde CARLOS MENDEZ")])
        assert "comentarios" not in parche

    def test_el_avance_se_queda_con_el_mayor(self):
        parche = dedup.parche_de_herencia(
            fila("PPC-1", CARLOS, avance=0.0),
            [fila("PPC-1", CARLOS_LARGO, avance=100.0)])
        assert parche["avance"] == 100.0

    def test_el_avance_de_la_conservada_no_baja(self):
        parche = dedup.parche_de_herencia(
            fila("PPC-1", CARLOS, avance=100.0),
            [fila("PPC-1", CARLOS_LARGO, avance=0.0)])
        assert "avance" not in parche

    def test_no_se_hereda_el_nombre_de_la_particion_que_se_borra(self):
        """
        Las 36 copias de César traen RESPONSABLE = "CESAR EDUARDO GARCIA AVALOS2":
        es el nombre de la hoja repetida, no un dato capturado.
        """
        parche = dedup.parche_de_herencia(
            fila("CE-0003", "CESAR EDUARDO GARCIA AVALOS", assignee_raw=None),
            [fila("CE-0003", "CESAR EDUARDO GARCIA AVALOS2",
                  assignee_raw="CESAR EDUARDO GARCIA AVALOS2", reloj="23.0")])
        assert "assignee_raw" not in parche
        assert parche["reloj"] == "23.0", "el resto de la copia sí se hereda"

    def test_las_columnas_de_identidad_nunca_se_heredan(self):
        parche = dedup.parche_de_herencia(
            fila("PPC-1", CARLOS, id="", dedupe_key=""),
            [fila("PPC-1", CARLOS_LARGO)])
        assert not ({"id", "dedupe_key", "source_sheet", "folio"} & set(parche))


class TestPlanDeConsolidacion:
    """El plan completo sobre filas con la forma de las reales."""

    @staticmethod
    def _plan(filas, alias=None, canonicas=None):
        hojas = {f["source_sheet"] for f in filas}
        rep = dedup.agrupar_particiones(hojas, alias)
        can = {rep[h]: c for h, c in (canonicas or {}).items() if h in rep}
        return dedup.plan_de_consolidacion(filas, rep, can)

    def test_el_duplicado_de_carlos_se_consolida_en_su_hoja(self):
        """El caso de la captura: dos filas, un folio, una persona."""
        filas = [fila("PPC-204747395", CARLOS), fila("PPC-204747395", CARLOS_LARGO)]
        plan = self._plan(filas, {CARLOS: [CARLOS, CARLOS_LARGO]}, {CARLOS: CARLOS})

        assert len(plan) == 1
        assert plan[0]["conservar"]["source_sheet"] == CARLOS
        assert [f["source_sheet"] for f in plan[0]["borrar"]] == [CARLOS_LARGO]

    def test_dos_personas_con_el_mismo_folio_no_son_duplicado(self):
        """Difusión lateral: RM-8909 vive en la tabla de cada involucrado."""
        filas = [fila("RM-8909", "RICARDO MENDO"), fila("RM-8909", CARLOS)]
        assert self._plan(filas) == []

    def test_dos_folios_distintos_de_la_misma_persona_no_son_duplicado(self):
        """Mismo CONCEPTO y misma FECHA, folios distintos: eso viene de la hoja."""
        filas = [fila("CM-0010", CARLOS), fila("CM-0011", CARLOS)]
        assert self._plan(filas) == []

    def test_una_fila_sin_folio_no_entra_al_plan(self):
        filas = [fila("", CARLOS), fila("", CARLOS_LARGO)]
        assert self._plan(filas, {CARLOS: [CARLOS, CARLOS_LARGO]}) == []

    def test_dos_filas_del_mismo_folio_en_la_misma_hoja_se_avisan_y_se_dejan(self):
        """
        La clave única lo impide, así que si aparece no lo produjo este defecto:
        elegir cuál sobra sería inventar.
        """
        filas = [fila("PPC-1", CARLOS), dict(fila("PPC-1", CARLOS), id="otro")]
        plan = self._plan(filas)

        assert len(plan) == 1
        assert plan[0]["conservar"] is None
        assert plan[0]["borrar"] == []
        assert "se deja intacto" in plan[0]["aviso"]

    def test_el_plan_conserva_el_avance_reportado_en_la_copia(self):
        filas = [fila("PPC-1", CARLOS, avance=0.0),
                 fila("PPC-1", CARLOS_LARGO, avance=100.0)]
        plan = self._plan(filas, {CARLOS: [CARLOS, CARLOS_LARGO]}, {CARLOS: CARLOS})

        assert plan[0]["parche"]["avance"] == 100.0

    def test_tres_copias_de_una_misma_tarea_dejan_una(self):
        filas = [fila("PPC-1", CARLOS), fila("PPC-1", CARLOS_LARGO),
                 fila("PPC-1", "CARLOS MENDEZ URBINA 2")]
        plan = self._plan(filas, {CARLOS: [CARLOS, CARLOS_LARGO]}, {CARLOS: CARLOS})

        assert len(plan[0]["borrar"]) == 2


class TestAplicar:
    """El orden de escritura: parche, hijos, fila."""

    class _MotorEspia:
        def __init__(self):
            self.eventos = []

        def upsert(self, tabla, filas, en_conflicto):
            self.eventos.append(("upsert", tabla, dict(filas[0])))
            return list(filas)

        def borrar(self, tabla, donde):
            self.eventos.append(("borrar", tabla, dict(donde)))

    def test_el_parche_se_escribe_antes_del_borrado(self):
        motor = self._MotorEspia()
        conservada = fila("PPC-1", CARLOS)
        borrada = fila("PPC-1", CARLOS_LARGO, avance=100.0)
        plan = [{"persona": CARLOS, "folio": "PPC-1", "conservar": conservada,
                 "borrar": [borrada], "parche": {"avance": 100.0}, "aviso": ""}]

        hechos = dedup.aplicar(motor, plan)

        acciones = [(e[0], e[1]) for e in motor.eventos]
        assert acciones == [("upsert", "tasks"),
                            ("borrar", "task_involucrados"),
                            ("borrar", "tasks")]
        assert hechos == {"parches": 1, "involucrados": 1, "borradas": 1}

    def test_el_parche_lleva_las_columnas_not_null_sin_default(self):
        """
        Un upsert con solo `{dedupe_key, parche}` responde 400 (23502): Postgres
        valida el NOT NULL sobre la tupla del INSERT antes de resolver el
        conflicto. Se comprobó contra la base real.
        """
        motor = self._MotorEspia()
        conservada = fila("PPC-1", CARLOS)
        dedup.aplicar(motor, [{"persona": CARLOS, "folio": "PPC-1",
                               "conservar": conservada,
                               "borrar": [fila("PPC-1", CARLOS_LARGO)],
                               "parche": {"reloj": "1"}, "aviso": ""}])

        enviado = next(e[2] for e in motor.eventos if e[0] == "upsert")
        assert {"dedupe_key", "folio", "concepto", "source_sheet"} <= set(enviado)
        assert enviado["source_sheet"] == CARLOS, "el parche no puede mover la fila"

    def test_el_borrado_va_acotado_por_id(self):
        """`PostgrestEngine.borrar` sin filtros borraría la tabla entera."""
        motor = self._MotorEspia()
        borrada = fila("PPC-1", CARLOS_LARGO)
        dedup.aplicar(motor, [{"persona": CARLOS, "folio": "PPC-1",
                               "conservar": fila("PPC-1", CARLOS),
                               "borrar": [borrada], "parche": {}, "aviso": ""}])

        borrados = [e[2] for e in motor.eventos if e[0] == "borrar" and e[1] == "tasks"]
        assert borrados == [{"id": borrada["id"]}]

    def test_un_grupo_avisado_no_escribe_nada(self):
        motor = self._MotorEspia()
        dedup.aplicar(motor, [{"persona": CARLOS, "folio": "PPC-1", "conservar": None,
                               "borrar": [], "parche": {}, "aviso": "se deja intacto"}])
        assert motor.eventos == []
