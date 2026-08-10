# language: es

Característica: Estatus final de una cotización terminada
  Cuando un vendedor deja una cotización al 100 % tiene que decir en qué
  terminó: perdida por tiempo, perdida por precio, cancelada por la planta,
  enviada o ganada. Sin ese dato los indicadores solo saben que la cotización
  se cerró, y el motivo —lo único accionable— se pierde.

  Esquema del escenario: Cuándo se le pide al vendedor elegir el cierre
    Dado que una cotización tiene el AVANCE en <avance>
    Y su columna ESTATUS dice <estatus>
    Cuando el vendedor guarda la cotización
    Entonces el sistema <decision> el selector de estatus final

    Ejemplos:
      | avance | estatus                | decision |
      | 100    | ""                     | abre     |
      | "100%" | "PENDIENTE"            | abre     |
      | 1      | "EN REVISION"          | abre     |
      | "100"  | "CANCELADA"            | abre     |
      | 100    | "GANADA"               | no abre  |
      | 100    | "Perdida x Precio"     | no abre  |
      | "100%" | "CANCELADA POR PLANTA" | no abre  |
      | 50     | ""                     | no abre  |
      | "1"    | ""                     | no abre  |

  Esquema del escenario: Cada cierre cuenta en el indicador que le toca
    Dado que una cotización cerró con el estatus <estatus>
    Cuando se calculan los indicadores de cotizaciones
    Entonces la cotización cuenta como <cubo>
    Y su motivo de cierre queda registrado como <motivo>

    Ejemplos:
      | estatus                | cubo       | motivo               |
      | "GANADA"               | ganada     | GANADA               |
      | "Perdida x Tiempo"     | perdida    | PERDIDA POR TIEMPO   |
      | "Perdida x Precio"     | perdida    | PERDIDA POR PRECIO   |
      | "Cancelada x Planta"   | perdida    | CANCELADA POR PLANTA |
      | "ENVIADA"              | en proceso | ENVIADA              |

  Escenario: Una cotización cerrada sin motivo se reporta aparte
    Dado que una cotización cerró con el estatus "CANCELADA"
    Cuando se calculan los indicadores de cotizaciones
    Entonces la cotización cuenta como perdida
    Y se contabiliza como cierre sin motivo
