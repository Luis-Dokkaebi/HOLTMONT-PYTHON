# language: es

Característica: El calendario del dashboard muestra el trabajo de cada quien
  El calendario semanal del inicio estaba vacío para todos. Dos causas: pedía la
  hoja equivocada y comparaba las fechas en un formato que la base ya no manda.
  Al arreglarlo, el dueño fijó la regla de quién ve qué (2026-08-15): una
  actividad aparece en el calendario de quien la **trabaja** —RESPONSABLE o
  VENDEDOR—, nunca en el de quien solo la asignó. Quien tiene tracker y
  cotizaciones ve las dos cosas, distinguibles, y cada una en su fecha: el
  tracker por FECHA y las cotizaciones por F. INICIO.

  Escenario: Quien asigna una actividad no la ve en su calendario
    Dado que "ANTONIA PINEDA LOPEZ" tiene en su tabla la actividad "LEVANTAMIENTO NAVE" a cargo de "SEBASTIAN PADILLA"
    Cuando "ANTONIA PINEDA LOPEZ" abre su calendario
    Entonces el calendario no muestra "LEVANTAMIENTO NAVE"

  Escenario: El responsable sí la ve en su calendario
    Dado que "SEBASTIAN PADILLA" tiene en su tabla la actividad "LEVANTAMIENTO NAVE" a cargo de "SEBASTIAN PADILLA"
    Cuando "SEBASTIAN PADILLA" abre su calendario
    Entonces el calendario muestra "LEVANTAMIENTO NAVE"

  Escenario: Una actividad sin responsable es de la tabla en la que está
    Dado que "ANTONIO SALAZAR" tiene en su tabla la actividad "REVISAR PLANOS" sin responsable
    Cuando "ANTONIO SALAZAR" abre su calendario
    Entonces el calendario muestra "REVISAR PLANOS"

  Escenario: Un vendedor ve su cotización marcada como tal y colocada en su F. INICIO
    Dado que "TERESA GARZA" tiene en su tabla de cotizaciones "COTIZAR OFICINAS" con F. INICIO "2026-08-10" a nombre de "TERESA GARZA"
    Cuando "TERESA GARZA" abre su calendario
    Entonces el calendario muestra "COTIZAR OFICINAS" con origen "COTIZACIONES" el día "2026-08-10"

  Escenario: Una actividad del tracker se coloca en su FECHA
    Dado que "TERESA GARZA" tiene en su tabla la actividad "REVISAR PRECIOS" con FECHA "2026-08-11" a cargo de "TERESA GARZA"
    Cuando "TERESA GARZA" abre su calendario
    Entonces el calendario muestra "REVISAR PRECIOS" con origen "TRACKER" el día "2026-08-11"
