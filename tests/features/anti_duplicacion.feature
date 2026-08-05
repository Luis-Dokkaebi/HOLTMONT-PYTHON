# language: es

Característica: Prevención de tareas duplicadas
  Para que un doble clic o una red lenta no generen dos filas idénticas, el
  sistema bloquea la repetición del mismo evento y sabe reencontrar una fila
  que perdió su FOLIO.

  Escenario: Un doble envío del mismo formulario crea una sola fila
    Dado que una tarea nueva "TAREA DOBLE CLICK" lleva el identificador temporal "tmp_123456"
    Cuando el formulario se envía cinco veces seguidas sin esperar respuesta
    Entonces existe exactamente una fila con el concepto "TAREA DOBLE CLICK"

  Escenario: El sistema devuelve la tarea guardada para que el tracker la fusione
    Dado que una tarea nueva "TAREA CON RESPUESTA" lleva el identificador temporal "tmp_998877"
    Cuando el formulario se envía una vez
    Entonces el sistema devuelve la tarea guardada con su FOLIO asignado

  Escenario: Si el FOLIO se perdió, la fila se reencuentra por CONCEPTO y FECHA
    Dado que existe una tarea "REVISION DE PLANOS" con fecha "10/07/26" a cargo de "JAIME OLIVO"
    Y que esa tarea se quedó sin FOLIO por un error de escritura
    Cuando llega una actualización para esa misma tarea con el comentario "COMENTARIO NUEVO"
    Entonces existe exactamente una fila con el concepto "REVISION DE PLANOS"
    Y la fila conserva el comentario "COMENTARIO NUEVO"
