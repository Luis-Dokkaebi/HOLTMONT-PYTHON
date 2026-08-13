# language: es

Característica: Reporte de bugs con evidencia que no se puede alterar
  Cualquier persona puede reportar una falla del sistema desde la plataforma y
  adjuntar un video de lo que le pasó. Lo que se reportó y lo que se adjuntó
  quedan como se enviaron: quien resuelve el ticket puede moverlo de estatus y
  escribir una nota, pero no puede reescribir el reporte original ni cambiar el
  video por otro.

  Escenario: Un reporte nuevo queda abierto y a nombre de quien lo envió
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Cuando el reporte se envía
    Entonces el ticket queda con estatus "ABIERTO"
    Y el ticket queda a nombre de "TERESA GARZA"

  Escenario: Quien resuelve no puede reescribir lo que se reportó
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Cuando quien resuelve intenta cambiar la descripción del ticket
    Entonces el sistema rechaza el cambio
    Y la descripción sigue siendo "El filtro semanal no guarda la fecha"

  Escenario: El video adjunto no se puede reemplazar, solo se pueden sumar más
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Y que al ticket se le adjunta la evidencia "video-original.mp4"
    Cuando se adjunta al ticket una segunda evidencia "captura-extra.png"
    Entonces el ticket conserva las dos evidencias en el orden en que se subieron
    Y la evidencia "video-original.mp4" sigue estando

  Escenario: Al cerrar un ticket queda registrado quién lo resolvió
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Cuando LUIS_CARLOS marca el ticket como "RESUELTO"
    Entonces el ticket queda a cargo de "LUIS_CARLOS" con su fecha de resolución
