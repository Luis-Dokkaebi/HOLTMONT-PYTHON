# language: es

Característica: Valores de respaldo en casillas con lista desplegable
  Las casillas ESTATUS y CUMPLIMIENTO tienen lista desplegable en la hoja. Una
  celda vacía rompe esa lista y deja la fila fuera de todos los conteos, así
  que el sistema nunca deja nacer una tarea sin ESTATUS.

  Escenario: Una tarea que llega sin ESTATUS nace con uno válido
    Dado que llega una tarea nueva "TAREA SIN ESTATUS" sin ESTATUS
    Cuando el sistema la guarda en la hoja "JAIME OLIVO"
    Entonces la fila guardada tiene ESTATUS "ASIGNADO"

  Escenario: El ESTATUS que sí viene se respeta tal cual
    Dado que llega una tarea nueva "TAREA CON ESTATUS" con ESTATUS "PENDIENTE"
    Cuando el sistema la guarda en la hoja "JAIME OLIVO"
    Entonces la fila guardada tiene ESTATUS "PENDIENTE"
