# language: es

Característica: Una persona, un tracker
  La misma persona aparece con dos nombres en el sistema: el de su hoja de
  tracker ("VANESSA DE LARA") y el completo con el que la registra el directorio
  ("ERIKA VANESSA RODRIGUEZ DE LARA"). Da igual con cuál se le asigne una
  actividad: tiene que caer donde ella la ve. Si cae en la otra hoja, el sistema
  reporta éxito y la actividad queda archivada donde nadie la abre.

  Escenario: Una actividad asignada con el nombre del directorio llega a su tracker
    Dado que "ERIKA VANESSA RODRIGUEZ DE LARA" es el nombre de directorio de "VANESSA DE LARA"
    Cuando se captura la actividad "PEDIR COTIZACION A PROVEEDOR" a cargo de "ERIKA VANESSA RODRIGUEZ DE LARA"
    Entonces la actividad queda en la hoja "VANESSA DE LARA"

  Escenario: Una actividad asignada con el nombre de la hoja llega al mismo sitio
    Dado que "ERIKA VANESSA RODRIGUEZ DE LARA" es el nombre de directorio de "VANESSA DE LARA"
    Cuando se captura la actividad "REVISAR ORDEN DE COMPRA" a cargo de "VANESSA DE LARA"
    Entonces la actividad queda en la hoja "VANESSA DE LARA"

  Escenario: Una actividad sin responsable se queda en la hoja de nadie
    Dado que "ERIKA VANESSA RODRIGUEZ DE LARA" es el nombre de directorio de "VANESSA DE LARA"
    Cuando se captura la actividad "REVISAR PENDIENTES" sin responsable
    Entonces la actividad queda en la hoja "ADMINISTRADOR"

  # Reporte del 2026-08-14, con captura del tracker de Carlos Méndez: cada
  # actividad aparecía dos veces. Al asignársela a sí mismo con su nombre de
  # directorio, el sistema lo tomaba por otra persona y escribía una copia en
  # una segunda hoja suya; su tracker muestra las dos hojas juntas, así que la
  # tarea salía duplicada.
  Escenario: Asignarse una actividad con su propio nombre de directorio no la duplica
    Dado que "CARLOS MENDEZ" asigna una actividad a "CARLOS MENDEZ URBINA"
    Entonces la actividad no se copia a ninguna otra tabla

  Escenario: Asignar a otra persona con su nombre de directorio llega a su tracker
    Dado que "CARLOS MENDEZ" asigna una actividad a "RICARDO ALONSO MENDO MORALES"
    Entonces la copia va a la tabla "RICARDO MENDO"

  Escenario: Una persona que el organigrama no conoce estrena su propia hoja
    Dado que "ERIKA VANESSA RODRIGUEZ DE LARA" es el nombre de directorio de "VANESSA DE LARA"
    Cuando se captura la actividad "REVISAR PLANOS" a cargo de "PERSONA NUEVA DEL EQUIPO"
    Entonces la actividad queda en la hoja "PERSONA NUEVA DEL EQUIPO"
