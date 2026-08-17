# language: es

Característica: El candado de alta es del Tracker
  Ninguna actividad nueva del Tracker nace sin PRIORIDAD, RIESGOS ni FEC. EST. FIN:
  sin esos tres datos nadie puede ordenar el trabajo ni medir el compromiso.

  Ventas no entra en esa regla. Ahí se capturan cotizaciones, que llevan otras
  columnas —Prio. cot., F. Visita, F. Inicio, F. Entrega—, así que pedir los tres
  campos deja a la vendedora sin poder dar de alta y sin dónde escribir lo que se
  le pide. Y no depende de qué columnas traiga la tabla ese día: la tabla de
  cotizaciones expone las que existan en la base, y una que se llame igual que
  uno de los tres campos no convierte a Ventas en Tracker.

  Escenario: Una actividad nueva del Tracker sin los tres campos no se guarda
    Dado que llega la actividad nueva "TAREA SIN CONTROL" sin PRIORIDAD, RIESGOS ni FEC. EST. FIN
    Cuando se intenta dar de alta en la hoja "JAIME OLIVO"
    Entonces el alta se rechaza nombrando PRIORIDAD, RIESGOS y FEC. EST. FIN
    Y no se escribe ninguna fila

  Escenario: La misma actividad con los tres campos sí se guarda
    Dado que llega la actividad nueva "TAREA CONTROLADA" con PRIORIDAD "URGENTE", RIESGOS "CATASTROFICO" y FEC. EST. FIN "30/08/26"
    Cuando se intenta dar de alta en la hoja "JAIME OLIVO"
    Entonces el alta se acepta

  Escenario: Una cotización nueva se da de alta sin esos tres campos
    Dado que llega la actividad nueva "COTIZAR NAVE INDUSTRIAL" sin PRIORIDAD, RIESGOS ni FEC. EST. FIN
    Cuando se intenta dar de alta en la hoja "ANTONIA_VENTAS"
    Entonces el alta se acepta

  Escenario: La tabla de cotizaciones trae esas columnas y sigue sin candado
    Dado que llega la actividad nueva "COTIZAR PLANTA 3" sin PRIORIDAD, RIESGOS ni FEC. EST. FIN
    Y que la hoja "ANTONIA_VENTAS" trae las columnas PRIORIDAD, RIESGOS y FEC. EST. FIN
    Cuando se intenta dar de alta en la hoja "ANTONIA_VENTAS"
    Entonces el alta se acepta
