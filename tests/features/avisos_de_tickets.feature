# language: es

Característica: Avisos a quien reporta un bug
  Quien reporta una falla no se queda sin saber qué pasó con ella. El sistema
  le avisa dentro de la plataforma cada vez que su reporte cambia de estado, y
  el aviso queda en su bandeja hasta que lo lee.

  Escenario: Al reportar una falla se recibe acuse de recibo
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Cuando el reporte se envía
    Entonces TERESA GARZA tiene 1 aviso sin leer
    Y su aviso más reciente dice "Recibimos tu reporte"

  Escenario: Cuando el reporte pasa a revisión se le avisa
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Cuando LUIS_CARLOS marca el ticket como "EN_REVISION"
    Entonces su aviso más reciente dice "Estamos trabajando en tu problema"
    Y TERESA GARZA tiene 2 avisos sin leer

  Escenario: Los avisos leídos dejan de contar
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Cuando TERESA GARZA lee sus avisos
    Entonces TERESA GARZA tiene 0 avisos sin leer

  Escenario: Nadie recibe los avisos de otra persona
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Cuando LUIS_CARLOS marca el ticket como "EN_REVISION"
    Entonces MIGUEL GALLARDO tiene 0 avisos sin leer

  Escenario: Si el aviso no se puede entregar, el reporte no se pierde
    Dado que TERESA GARZA reporta el problema "El filtro semanal no guarda la fecha" en el módulo "PPC"
    Y que el sistema de avisos está caído
    Cuando el reporte se envía
    Entonces el ticket queda con estatus "ABIERTO"
    Y TERESA GARZA tiene 0 avisos sin leer
