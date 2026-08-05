# language: es

Característica: Ruteo de tareas y la Ley de Antonia
  Para que la tabla maestra de ventas no se contamine con tareas del tracker
  general, el sistema decide la hoja destino según quién guarda la tarea.

  Escenario: Un compañero cualquiera no escribe en la tabla de ventas de otro
    Dado que el usuario "LUIS_CARLOS" trabaja en el tracker general
    Cuando guarda una tarea en la hoja "EDUARDO MANZANARES (VENTAS)"
    Entonces la tarea queda en la hoja "EDUARDO MANZANARES"
    Y el sufijo "(VENTAS)" desaparece de la hoja destino

  Escenario: El titular sí conserva su propia tabla de ventas
    Dado que el usuario "ANGEL_SALINAS" trabaja en el tracker general
    Cuando guarda una tarea en la hoja "ANGEL SALINAS (VENTAS)"
    Entonces la tarea queda en la hoja "ANGEL SALINAS (VENTAS)"
    Y la hoja destino no fue redirigida

  Escenario: La tabla maestra de ventas está protegida de usuarios ajenos
    Dado que el usuario "EDUARDO_MANZANARES" trabaja en el tracker general
    Cuando guarda una tarea en la hoja "ANTONIA_VENTAS"
    Entonces la tarea queda en la hoja "ANTONIA PINEDA LOPEZ"
    Y el motivo de la redirección es "CORE_VENTAS_PROTEGIDO"
