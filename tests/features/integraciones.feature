# language: es

Característica: Fechas íntegras hacia el correo de avisos
  El servicio que arma los correos solo interpreta bien la fecha si llega
  completa: con milisegundos y con la "Z" al final. Recortarla desplaza la hora
  del aviso y la gente recibe recordatorios a deshora.

  Escenario: La fecha de inicio del aviso conserva milisegundos y la Z
    Dado que una tarea "VISITA A PLANTA" inicia el "05/08/26"
    Cuando el sistema prepara el aviso para esa tarea
    Entonces la fecha de inicio del aviso termina en "Z"
    Y la fecha de inicio del aviso conserva los milisegundos

  Escenario: El aviso identifica de qué tarea habla
    Dado que una tarea "VISITA A PLANTA" inicia el "05/08/26"
    Cuando el sistema prepara el aviso para esa tarea
    Entonces el aviso menciona el concepto "VISITA A PLANTA"
