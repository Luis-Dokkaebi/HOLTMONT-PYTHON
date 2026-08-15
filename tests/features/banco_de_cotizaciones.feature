# language: es

Característica: El Banco de Cotizaciones agrupa por F. INICIO
  El banco ordena las cotizaciones de la base por año y mes, y dentro de cada mes
  por cliente. La fecha que decide el periodo es F. INICIO (decisión del dueño,
  2026-08-15): una cotización que arranca el 1 de julio pertenece a julio, aunque
  se haya capturado o visitado en otro mes. Es la misma regla que ya gobierna el
  calendario del dashboard.

  Una cotización repartida vive en dos tablas —la de quien la reparte y la de
  quien la trabaja—, y en el banco es una sola cotización.

  Escenario: La cotización cuelga del mes de su F. INICIO
    Dado que "DANFOSS 2" tiene la cotización "AV-1222" con F. INICIO "2026-06-01" en "ANTONIA_VENTAS"
    Cuando se abre el banco de "Junio" de "2026"
    Entonces el banco muestra al cliente "DANFOSS 2"

  Escenario: Una cotización de otro mes no aparece en el periodo
    Dado que "ALCOM" tiene la cotización "AV-1400" con F. INICIO "2026-07-02" en "ANTONIA_VENTAS"
    Cuando se abre el banco de "Junio" de "2026"
    Entonces el banco no muestra al cliente "ALCOM"

  Escenario: Las cotizaciones de los vendedores también forman el banco
    Dado que "MARMON FOOD" tiene la cotización "RR-0007" con F. INICIO "2026-06-11" en "RAMIRO RODRIGUEZ (VENTAS)"
    Cuando se abre el banco de "Junio" de "2026"
    Entonces el banco muestra al cliente "MARMON FOOD"

  Escenario: Una cotización repartida cuenta una sola vez
    Dado que "DANFOSS 2" tiene la cotización "AV-1222" con F. INICIO "2026-06-01" en "ANTONIA_VENTAS"
    Y que "DANFOSS 2" tiene la cotización "AV-1222" con F. INICIO "2026-06-01" en "RAMIRO RODRIGUEZ (VENTAS)"
    Cuando se abre el banco de "Junio" de "2026"
    Entonces el banco cuenta 1 cotización para el cliente "DANFOSS 2"
