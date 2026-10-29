# language: es

Característica: El semáforo de la pantalla de pared
  La televisión colgada de cada persona pinta sus fechas y sus DÍAS con los
  mismos colores que la hoja de Google: verde a tiempo, amarillo por vencer y
  rojo vencida. Los días se cuentan desde la fecha de inicio hasta hoy, y el
  límite de cada color depende de la clasificación de la actividad.

  Esquema del escenario: El color depende de la clasificación y de los días
    Dado una actividad pendiente con clasificación <clasificacion> que empezó hace <dias> días
    Cuando la pantalla de pared prepara la tabla
    Entonces sus DÍAS se pintan de <color>

    Ejemplos:
      | clasificacion | dias | color    |
      | A             | 1    | verde    |
      | A             | 2    | amarillo |
      | A             | 4    | rojo     |
      | AA            | 11   | verde    |
      | AA            | 12   | amarillo |
      | AA            | 15   | rojo     |
      | AAA           | 24   | verde    |
      | AAA           | 25   | amarillo |
      | AAA           | 31   | rojo     |

  Escenario: Los días se cuentan hasta hoy y no se copian de lo guardado
    Dado una actividad pendiente con clasificación AA que empezó hace 20 días
    Y la hoja tiene guardado 3 en su columna RELOJ
    Cuando la pantalla de pared prepara la tabla
    Entonces la pantalla muestra 20 días
    Y sus DÍAS se pintan de rojo

  Escenario: Sin clasificación no se inventa un color
    Dado una actividad pendiente sin clasificación que empezó hace 40 días
    Cuando la pantalla de pared prepara la tabla
    Entonces la pantalla muestra 40 días
    Y sus DÍAS no llevan color

  Escenario: Lo terminado no se pinta de rojo
    Dado una actividad terminada con clasificación A que empezó hace 40 días
    Cuando la pantalla de pared prepara la tabla
    Entonces sus DÍAS no llevan color
