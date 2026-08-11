# language: es

Característica: La Pre Work Order reparte su programa en el Tracker
  Una orden de trabajo no la ejecuta una sola persona: su programa detalla, por
  renglón, qué se hace, quién lo hace y para cuándo. Cada renglón se convierte
  en una tarea en el tracker de su responsable, sin dejar de estar anclada a la
  orden que la originó.

  Escenario: Cada renglón del programa llega al tracker de su responsable
    Dado un programa de Pre Work Order con los renglones:
      | descripcion       | seccion         | responsable   |
      | MONTAR TABLERO    | TRABAJO         | TERESA GARZA  |
      | CABLEAR CHAROLA   | PRECONSTRUCCION | ANGEL SALINAS |
    Cuando la orden se reparte en el Tracker
    Entonces "TERESA GARZA" recibe la tarea "MONTAR TABLERO" en su tracker
    Y "ANGEL SALINAS" recibe la tarea "CABLEAR CHAROLA" en su tracker

  Escenario: Un renglón compartido genera una tarea para cada responsable
    Dado un programa de Pre Work Order con los renglones:
      | descripcion    | seccion | responsable                  |
      | MONTAR TABLERO | TRABAJO | TERESA GARZA, ANGEL SALINAS  |
    Cuando la orden se reparte en el Tracker
    Entonces el reparto produce 2 tareas
    Y "TERESA GARZA" recibe la tarea "MONTAR TABLERO" en su tracker
    Y "ANGEL SALINAS" recibe la tarea "MONTAR TABLERO" en su tracker

  Escenario: Un renglón sin responsable no le cae a nadie
    Dado un programa de Pre Work Order con los renglones:
      | descripcion    | seccion | responsable |
      | MONTAR TABLERO | TRABAJO |             |
    Cuando la orden se reparte en el Tracker
    Entonces el reparto produce 0 tareas

  Escenario: Los renglones en blanco del formulario no siembran tareas
    Dado un programa de Pre Work Order con los renglones:
      | descripcion | seccion | responsable  |
      |             | VISITA  | TERESA GARZA |
    Cuando la orden se reparte en el Tracker
    Entonces el reparto produce 0 tareas

  Escenario: El trabajo de un vendedor va a su tracker, nunca a sus cotizaciones
    Dado un programa de Pre Work Order con los renglones:
      | descripcion    | seccion | responsable      |
      | MONTAR TABLERO | TRABAJO | SEBASTIAN PADILLA |
    Cuando la orden se reparte en el Tracker
    Entonces ninguna tarea del reparto cae en una tabla de ventas

  Escenario: Una línea de programa no se confunde con una fase de cotización
    Dado un programa de Pre Work Order con los renglones:
      | descripcion    | seccion | responsable  |
      | MONTAR TABLERO | VISITA  | TERESA GARZA |
    Cuando la orden se reparte en el Tracker
    Entonces ninguna tarea del reparto se toma por una fase de papa caliente

  Escenario: Una orden sin clasificación del Tracker se rechaza entera
    Dado una Pre Work Order con clasificación "Media"
    Cuando se guarda la orden
    Entonces el guardado falla avisando de la clasificación
    Y no queda ninguna tarea guardada
