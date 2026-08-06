# language: es

Característica: Una celda numérica en una columna de texto
  La vista edita RELOJ con un campo numérico y la rellena sola: una fila nueva
  nace con 0 y el contador de días la reescribe en cada carga. En la hoja daba
  igual, porque una celda de Sheets acepta cualquier tipo; en la base RELOJ es
  texto. Rechazar ese número tumbaba el lote entero, así que no se podía dar de
  alta una cotización ni cerrar una actividad al 100 %.

  Escenario: Una cotización recién creada trae RELOJ en cero
    Dado que llega una cotización nueva con RELOJ numérico 0
    Cuando el sistema la valida para guardarla
    Entonces se acepta y RELOJ vale "0"

  Escenario: El contador de días reescribe RELOJ en una actividad
    Dado que llega una actividad con RELOJ numérico 12
    Cuando el sistema la valida para guardarla
    Entonces se acepta y RELOJ vale "12"

  Escenario: Una hora escrita a mano se conserva sin tocar
    Dado que llega una actividad con RELOJ de texto "17:00:00"
    Cuando el sistema la valida para guardarla
    Entonces se acepta y RELOJ vale "17:00:00"

  Escenario: Cerrar al 100 % una actividad cuyo RELOJ es un número la archiva
    Dado que la actividad "REVISAR PLANOS" está al 0 % con RELOJ numérico 3
    Cuando el usuario le pone 100 % y guarda
    Entonces la actividad queda bajo TAREAS REALIZADAS
