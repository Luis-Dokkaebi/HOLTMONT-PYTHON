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

  Escenario: La clave interna de la base nunca se guarda como folio
    Dado que la actividad "PROYECTO 3459 REUBICACION DE PUERTA" tiene el folio "RC-0170" y la clave interna "b90ed1a7-7c3f-4d21-9a55-1f0c2e4b8a77"
    Y que quien la recibe estrena su tabla, que todavía no tiene ninguna fila
    Cuando la actividad se guarda en la tabla de quien la recibe
    Entonces la fila guardada lleva el folio "RC-0170"
    Y la tabla de quien la recibe tiene una sola fila

  Escenario: Si el FOLIO se perdió, la fila se reencuentra por CONCEPTO y FECHA
    Dado que existe una tarea "REVISION DE PLANOS" con fecha "10/07/26" a cargo de "JAIME OLIVO"
    Y que esa tarea se quedó sin FOLIO por un error de escritura
    Cuando llega una actualización para esa misma tarea con el comentario "COMENTARIO NUEVO"
    Entonces existe exactamente una fila con el concepto "REVISION DE PLANOS"
    Y la fila conserva el comentario "COMENTARIO NUEVO"
