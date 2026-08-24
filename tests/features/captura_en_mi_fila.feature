# language: es

Característica: Lo que capturo se guarda en la fila que yo veo
  Cuando alguien me asigna una actividad, esa actividad existe dos veces: la
  fila de quien me la asignó y la mía, en mi tracker. Los folios del PPC llevan
  prefijo de secuencia global (PPC-), así que las dos filas comparten folio y se
  distinguen solo por la hoja en la que viven.

  Al editar la mía —poner el porcentaje de avance, anotar la restricción— el
  guardado tiene que escribir en MI fila. Si escribe en la del otro, el sistema
  contesta «Guardado exitoso», mi captura no está en ningún sitio que yo abra y
  al recargar vuelven los valores viejos.

  # Reporte del 2026-08-22 (BUG-0015, ALFONSO CORREA): «de la celda 3 al 7 se le
  # agregó los porcentajes y comentarios y no se actualiza».
  Escenario: El avance y la restricción que capturo quedan en mi fila
    Dado que "GERALDINE MORALES" le asignó a "ALFONSO CORREA" la actividad "PPC-5442804"
    Cuando "ALFONSO CORREA" le pone 10 % de avance y la restricción "EN ESPERA DE LLAMADA"
    Entonces su tracker muestra 10 % de avance en "PPC-5442804"
    Y su tracker muestra la restricción "EN ESPERA DE LLAMADA"

  Escenario: Mi captura no reescribe la fila de quien me asignó la actividad
    Dado que "GERALDINE MORALES" le asignó a "ALFONSO CORREA" la actividad "PPC-5442804"
    Cuando "ALFONSO CORREA" le pone 10 % de avance y la restricción "EN ESPERA DE LLAMADA"
    Entonces la fila de "GERALDINE MORALES" conserva su restricción vacía

  Escenario: Editar la actividad no estrena una fila más
    Dado que "GERALDINE MORALES" le asignó a "ALFONSO CORREA" la actividad "PPC-5442804"
    Cuando "ALFONSO CORREA" le pone 10 % de avance y la restricción "EN ESPERA DE LLAMADA"
    Entonces existen 2 filas con el folio "PPC-5442804"
