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

  Escenario: Una persona que el organigrama no conoce estrena su propia hoja
    Dado que "ERIKA VANESSA RODRIGUEZ DE LARA" es el nombre de directorio de "VANESSA DE LARA"
    Cuando se captura la actividad "REVISAR PLANOS" a cargo de "PERSONA NUEVA DEL EQUIPO"
    Entonces la actividad queda en la hoja "PERSONA NUEVA DEL EQUIPO"
