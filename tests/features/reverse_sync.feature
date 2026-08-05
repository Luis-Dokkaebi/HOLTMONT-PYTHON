# language: es

Característica: Sincronización de vuelta hacia la tabla de ventas
  Cuando una tarea nació en la tabla maestra de ventas (su FOLIO empieza por
  "AV-"), el avance que registre cualquier compañero debe reflejarse de vuelta
  en esa tabla maestra. Si no, Antonia ve datos viejos.

  Escenario: El avance de un compañero vuelve a la tabla maestra
    Dado que la tarea "COTIZAR NAVE" tiene el FOLIO "AV-00123"
    Cuando "JAIME OLIVO" la deja con ESTATUS "TERMINADO" y AVANCE 1
    Entonces la tabla maestra recibe el ESTATUS "TERMINADO"
    Y la tabla maestra conserva el mismo FOLIO "AV-00123"

  Escenario: El CUMPLIMIENTO del compañero no contamina la tabla maestra
    Dado que la tarea "COTIZAR NAVE" tiene el FOLIO "AV-00123"
    Cuando "JAIME OLIVO" la deja con ESTATUS "TERMINADO" y AVANCE 1
    Entonces la tabla maestra no recibe la casilla "CUMPLIMIENTO"

  Escenario: Una tarea sin FOLIO no puede volver a ninguna parte
    Dado que la tarea "TAREA SUELTA" no tiene FOLIO
    Cuando "JAIME OLIVO" la deja con ESTATUS "TERMINADO" y AVANCE 1
    Entonces el sistema no envía nada a la tabla maestra
