# language: es

Característica: El recorrido de un prospecto por el embudo comercial
  Un negocio del mapa no es todavía un prospecto: es un punto. Se vuelve
  prospecto cuando alguien lo marca, y desde ahí recorre cuatro momentos —recién
  encontrado, ya contactado, cotizando y descartado—.

  Lo que el sistema tiene que sostener es que ese recorrido sea uno solo por
  negocio y que no se pierda por el camino: si el mismo negocio pudiera tener dos
  estados a la vez, dos personas de Compras lo llamarían creyendo cada una que
  era la primera.

  Escenario: Un negocio del mapa entra al embudo como recién encontrado
    Dado el negocio "FERRETERIA EL TORNILLO" del mapa, sin marcar
    Cuando Compras lo marca como "NUEVO"
    Entonces el negocio queda en "NUEVO"
    Y queda registrado el día en que entró al embudo

  Escenario: Un negocio recorre el embudo sin perder su fecha de entrada
    Dado el negocio "FERRETERIA EL TORNILLO" del mapa, sin marcar
    Cuando Compras lo marca como "NUEVO"
    Y Compras lo marca como "CONTACTADO"
    Y Compras lo marca como "COTIZANDO"
    Entonces el negocio queda en "COTIZANDO"
    Y el día en que entró al embudo es el mismo del principio

  Escenario: El mismo negocio no puede llevar dos estados a la vez
    Dado el negocio "FERRETERIA EL TORNILLO" del mapa, sin marcar
    Cuando Compras lo marca como "NUEVO"
    Y Compras lo marca como "CONTACTADO"
    Entonces hay un solo registro de ese negocio

  Escenario: Un negocio descartado puede volver al embudo
    Dado el negocio "FERRETERIA EL TORNILLO" del mapa, sin marcar
    Cuando Compras lo marca como "DESCARTADO"
    Y Compras lo marca como "CONTACTADO"
    Entonces el negocio queda en "CONTACTADO"

  Escenario: Al marcarlo se anota quién lo lleva y qué se acordó
    Dado el negocio "FERRETERIA EL TORNILLO" del mapa, sin marcar
    Cuando Compras lo marca como "CONTACTADO" a nombre de "RAMIRO RODRIGUEZ" con la nota "Pidió catálogo de tubería"
    Entonces el negocio lo lleva "RAMIRO RODRIGUEZ"
    Y la nota del negocio dice "Pidió catálogo de tubería"

  Escenario: Un momento que no existe en el embudo se rechaza
    Dado el negocio "FERRETERIA EL TORNILLO" del mapa, sin marcar
    Cuando Compras intenta marcarlo como "PERDIDO"
    Entonces el sistema rechaza el momento desconocido
    Y el negocio sigue sin marcar
