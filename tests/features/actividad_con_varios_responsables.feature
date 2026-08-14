# language: es

Característica: Una actividad asignada a varias personas
  Una misma actividad puede repartirse entre varios compañeros: un folio, un
  concepto y una fila en la tabla de cada quien. El avance es de cada persona,
  así que terminar la mía no termina la tuya, y guardar la mía no revive la
  tuya. La actividad se da por cerrada cuando TODOS terminan, que es la misma
  regla que ya rige las fases de una cotización.

  Antecedentes:
    Dado que "ANTONIO SALAZAR" reparte la actividad "REVISAR PLANOS" entre "GERALDINE MARTINEZ" y "MIGUEL GALLARDO"

  Escenario: Terminar la mía no le cierra el trabajo al compañero
    Cuando "GERALDINE MARTINEZ" reporta 100 % en su tabla
    Entonces la actividad queda terminada para "GERALDINE MARTINEZ"
    Y la actividad sigue en operativo para "MIGUEL GALLARDO"

  Escenario: El avance del compañero no me devuelve a operativo lo ya terminado
    Cuando "GERALDINE MARTINEZ" reporta 100 % en su tabla
    Y "MIGUEL GALLARDO" reporta 30 % en su tabla
    Entonces la actividad queda terminada para "GERALDINE MARTINEZ"
    Y la actividad sigue en operativo para "MIGUEL GALLARDO"

  Escenario: Quien asignó ve el avance del más atrasado hasta que todos terminan
    Cuando "GERALDINE MARTINEZ" reporta 100 % en su tabla
    Y "MIGUEL GALLARDO" reporta 30 % en su tabla
    Entonces la actividad sigue en operativo para "ANTONIO SALAZAR"
    Y la fila de "ANTONIO SALAZAR" muestra 30 % de avance

  Escenario: La actividad se cierra cuando termina el último
    Cuando "GERALDINE MARTINEZ" reporta 100 % en su tabla
    Y "MIGUEL GALLARDO" reporta 100 % en su tabla
    Entonces la actividad queda terminada para "ANTONIO SALAZAR"
