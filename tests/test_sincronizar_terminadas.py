"""
Pruebas de `scripts/sincronizar_terminadas.py`.

El script concilia dos verdades sobre qué es una tarea «terminada»:

* En la **hoja** es una posición: arriba las activas, un hueco, y debajo la
  sección de realizadas. No hay rótulo; ninguna de las 40 hojas escribe
  «TAREAS REALIZADAS», solo dejan filas vacías.
* En la **base** es una propiedad calculada de la fila (`_esta_archivada`).

Discrepan en 210 filas que su dueño bajó a realizadas sin tocarles el AVANCE, y
en 959 copias de un mismo folio donde una está cerrada y la otra no. Cada caso
de aquí sale de una de esas dos patologías medidas, no de una hipótesis.
"""

from __future__ import annotations

import importlib.util
import pathlib

import openpyxl
import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _cargar_modulo():
    """El script vive en `scripts/`, que no es un paquete importable."""
    ruta = RAIZ / "scripts" / "sincronizar_terminadas.py"
    spec = importlib.util.spec_from_file_location("sincronizar_terminadas", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


sync = _cargar_modulo()


def _hoja(folios_por_fila):
    """Hoja con encabezado en la fila 10 y folios en las filas indicadas."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.cell(10, 1, "Folio")
    for fila, folio in folios_por_fila.items():
        hoja.cell(fila, 1, folio)
    return hoja


class TestSepararPorHueco:
    """El separador de la hoja es un hueco, no un rótulo."""

    def test_parte_en_el_primer_hueco_grande(self):
        """
        La hoja de Geraldine: nueve activas en 11-19, vacío hasta 274, y el
        histórico desde 275.
        """
        hoja = _hoja({**{r: f"GM-{r}" for r in range(11, 20)},
                      **{r: f"GM-{r}" for r in range(275, 280)}})
        arriba, abajo = sync.separar_por_hueco(hoja, 10)
        assert arriba == list(range(11, 20))
        assert abajo == list(range(275, 280))

    def test_un_renglon_suelto_en_blanco_no_parte_la_hoja(self):
        """
        Hay hojas con una o dos filas vacías entre bloques que no son el
        separador. Cortar ahí mandaría el bloque activo a realizadas.
        """
        hoja = _hoja({11: "A-1", 12: "A-2", 14: "A-3", 15: "A-4"})
        arriba, abajo = sync.separar_por_hueco(hoja, 10)
        assert arriba == [11, 12, 14, 15]
        assert abajo == []

    def test_una_hoja_sin_hueco_no_tiene_seccion_de_realizadas(self):
        hoja = _hoja({r: f"A-{r}" for r in range(11, 16)})
        arriba, abajo = sync.separar_por_hueco(hoja, 10)
        assert arriba == list(range(11, 16))
        assert abajo == []

    def test_una_hoja_vacia_no_revienta(self):
        assert sync.separar_por_hueco(_hoja({}), 10) == ([], [])


class TestDesajustesPorSeparador:
    def test_una_fila_bajo_el_separador_y_abierta_se_detecta(self):
        filas = [{"dedupe_key": "k1", "folio": "GM-1", "source_sheet": "HOJA",
                  "avance": 10.0, "status": "ASIGNADO", "cumplimiento": None}]
        assert sync.desajustes_por_separador(filas, {"HOJA": {"GM-1"}}) == filas

    def test_una_fila_bajo_el_separador_pero_ya_cerrada_se_deja(self):
        filas = [{"dedupe_key": "k1", "folio": "GM-1", "source_sheet": "HOJA",
                  "avance": 100.0, "status": "ASIGNADO", "cumplimiento": None}]
        assert sync.desajustes_por_separador(filas, {"HOJA": {"GM-1"}}) == []

    def test_una_fila_de_arriba_no_se_toca(self):
        """Está en operativo en la hoja: cerrarla sería inventar el cierre."""
        filas = [{"dedupe_key": "k1", "folio": "GM-9", "source_sheet": "HOJA",
                  "avance": 10.0, "status": "ASIGNADO", "cumplimiento": None}]
        assert sync.desajustes_por_separador(filas, {"HOJA": {"GM-1"}}) == []

    def test_el_nombre_de_hoja_se_compara_normalizado(self):
        """
        `source_sheet` no está normalizado: hay hojas con espacio inicial
        (` LILIANA AYLIN MARTINEZ IBARRA`) y capitalización mixta.
        """
        filas = [{"dedupe_key": "k1", "folio": "GM-1", "source_sheet": " Hoja  Rara ",
                  "avance": 0.0, "status": "ASIGNADO", "cumplimiento": None}]
        assert len(sync.desajustes_por_separador(filas, {"HOJA RARA": {"GM-1"}})) == 1


class TestCopiasDesincronizadas:
    def _fila(self, clave, hoja, avance, concepto="Actividad normal"):
        return {"dedupe_key": clave, "folio": "PPC-1", "source_sheet": hoja,
                "avance": avance, "status": "ASIGNADO", "cumplimiento": None,
                "concepto": concepto}

    def test_la_copia_abierta_toma_el_cierre_de_su_hermana(self):
        """
        El caso real: la fila del PPC maestro quedó en 0 % y la de la persona
        que hizo el trabajo en 100 %.
        """
        abierta = self._fila("PPC-1", "ADMINISTRADOR", 0.0)
        cerrada = self._fila("ZAIRA::PPC-1", "ZAIRA", 100.0)
        pendientes = sync.copias_desincronizadas([abierta, cerrada])
        assert pendientes == [(abierta, cerrada)]

    def test_sin_hermana_cerrada_no_se_cierra_nada(self):
        """Si todas están abiertas, inventar un cierre sería falsear el dato."""
        filas = [self._fila("PPC-1", "A", 10.0), self._fila("B::PPC-1", "B", 20.0)]
        assert sync.copias_desincronizadas(filas) == []

    def test_un_folio_con_una_sola_fila_no_es_una_copia(self):
        assert sync.copias_desincronizadas([self._fila("PPC-1", "A", 0.0)]) == []

    def test_gana_la_hermana_mas_avanzada(self):
        abierta = self._fila("PPC-1", "A", 0.0)
        filas = [abierta,
                 self._fila("B::PPC-1", "B", 100.0),
                 self._fila("C::PPC-1", "C", 100.0)]
        (_, modelo), = sync.copias_desincronizadas(filas)
        assert float(modelo["avance"]) == 100.0

    def test_una_microtarea_de_papa_caliente_nunca_propaga(self):
        """
        Comparten folio entre sí y con la cotización: propagar pondría el 100 %
        de una fase encima del trabajo pendiente de otra persona. Misma
        frontera que traza `campos_sincronizables`.
        """
        abierta = self._fila("PPC-1", "A", 0.0, concepto="Cotizar nave [Calculo y Diseño]")
        cerrada = self._fila("B::PPC-1", "B", 100.0)
        assert sync.copias_desincronizadas([abierta, cerrada]) == []


class TestFilaDeCierre:
    BASE = {"dedupe_key": "k1", "folio": "GM-1", "concepto": "Algo",
            "source_sheet": "HOJA", "avance": 10.0, "status": "ASIGNADO",
            "cumplimiento": None}

    def test_sin_modelo_cierra_por_la_regla_de_la_hoja(self):
        carga = sync.fila_de_cierre(dict(self.BASE))
        assert carga["avance"] == 100
        assert carga["cumplimiento"] == "SI"

    def test_con_modelo_copia_el_estado_de_la_hermana(self):
        modelo = {"avance": 100.0, "status": "TERMINADA", "cumplimiento": "SI"}
        carga = sync.fila_de_cierre(dict(self.BASE), modelo)
        assert carga["avance"] == 100.0
        assert carga["status"] == "TERMINADA"

    def test_no_copia_los_campos_vacios_del_modelo(self):
        """Mandar `None` a una columna NOT NULL aborta el lote con un 23502."""
        modelo = {"avance": 100.0, "status": "", "cumplimiento": None}
        carga = sync.fila_de_cierre(dict(self.BASE), modelo)
        assert "status" not in carga
        assert "cumplimiento" not in carga

    @pytest.mark.parametrize("columna", ["folio", "concepto", "source_sheet"])
    def test_reenvia_las_obligatorias(self, columna):
        """
        Un upsert valida las NOT NULL sobre la tupla del INSERT **antes** de
        resolver el conflicto, así que hay que mandarlas aunque no cambien.
        """
        assert columna in sync.fila_de_cierre(dict(self.BASE))

    def test_la_identidad_siempre_viaja(self):
        assert sync.fila_de_cierre(dict(self.BASE))["dedupe_key"] == "k1"
