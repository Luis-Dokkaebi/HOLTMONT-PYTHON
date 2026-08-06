# language: es

Característica: A dónde va una cotización asignada
  Una cotización solo puede caer en una tabla con sufijo (VENTAS). Si la persona
  no tiene una, no hay a dónde mandarlo y no debe ofrecerse como destino: una
  cotización no se filtra al tracker de nadie. Repartirlas es cosa de Toñita.

  Escenario: Toñita asigna una cotización a un vendedor con tabla
    Dado que Toñita reparte una cotización a "TERESA GARZA"
    Entonces la copia va a la tabla "TERESA GARZA (VENTAS)"

  Escenario: El sufijo ya escrito no se duplica
    Dado que Toñita reparte una cotización a "TERESA GARZA (VENTAS)"
    Entonces la copia va a la tabla "TERESA GARZA (VENTAS)"

  Escenario: Toñita asigna a alguien sin tabla de cotizaciones
    Dado que Toñita reparte una cotización a "ALFONSO CORREA"
    Entonces no hay ninguna tabla destino

  Escenario: La cotización no se filtra al tracker de quien no vende
    Dado que Toñita reparte una cotización a "GERALDINE MARTINEZ HERNANDEZ"
    Entonces no hay ninguna tabla destino

  Escenario: Un vendedor no reparte cotizaciones
    Dado que el vendedor "SEBASTIAN PADILLA" reparte una cotización a "TERESA GARZA"
    Entonces no hay ninguna tabla destino

  Escenario: Asignar una actividad del tracker sigue igual
    Dado que "JAIME OLIVO" asigna una actividad a "GERALDINE MARTINEZ HERNANDEZ"
    Entonces la copia va a la tabla "GERALDINE MARTINEZ HERNANDEZ"
