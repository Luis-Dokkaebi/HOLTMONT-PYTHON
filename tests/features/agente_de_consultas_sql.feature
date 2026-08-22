# language: es

Característica: El agente nunca ejecuta una consulta que escriba
  La consulta la redacta un modelo de lenguaje a partir de lo que alguien
  escribe en un cuadro de texto. Eso significa que la instrucción y el dato
  viajan por el mismo canal, y que ninguna de las dos cosas es de fiar.

  El agente es de consulta: lee y responde. Cualquier cosa que modifique o
  borre información se rechaza antes de llegar a la base, y también se rechaza
  leer tablas que no son las suyas —una consulta al padrón de usuarios es tan
  SELECT como cualquier otra—.

  Esquema del escenario: Una consulta que modifica datos se rechaza
    Dado que el agente consulta la tabla de actividades
    Cuando el modelo propone la consulta "<consulta>"
    Entonces la consulta se rechaza antes de tocar la base

    Ejemplos:
      | consulta                                  |
      | DELETE FROM tasks                         |
      | UPDATE tasks SET avance = 100             |
      | DROP TABLE tasks                          |
      | SELECT * FROM tasks; DROP TABLE tasks     |
      | SELECT * FROM auth.users                  |

  Escenario: Una consulta legítima de lectura sí se ejecuta
    Dado que el agente consulta la tabla de actividades
    Cuando el modelo propone la consulta "SELECT departamento, COUNT(*) FROM tasks GROUP BY 1"
    Entonces la consulta se ejecuta contra la base

  Escenario: El resultado que vuelve de la base viene acotado
    Dado que el agente consulta la tabla de actividades
    Cuando el modelo propone la consulta "SELECT * FROM tasks"
    Entonces la consulta que llega a la base trae un límite de filas
