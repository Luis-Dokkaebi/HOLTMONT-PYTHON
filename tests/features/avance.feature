# language: es

Característica: Interpretación del porcentaje de AVANCE
  La hoja de cálculo devuelve el número 1 para una celda con formato de
  porcentaje al 100 %. Confundirlo con "1 %" archiva tareas que siguen abiertas
  y corrompe todos los indicadores del tracker.

  Esquema del escenario: Valores de AVANCE que significan tarea terminada
    Dado que la casilla AVANCE de una tarea contiene <valor>
    Cuando el sistema evalúa si la tarea está terminada
    Entonces la respuesta es <terminada>

    Ejemplos:
      | valor  | terminada |
      | 1      | sí        |
      | 100    | sí        |
      | "100"  | sí        |
      | "100%" | sí        |
      | "1"    | no        |
      | "1.0"  | no        |
      | 0.5    | no        |
      | ""     | no        |
