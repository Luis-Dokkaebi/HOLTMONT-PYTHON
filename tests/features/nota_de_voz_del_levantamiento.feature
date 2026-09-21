# language: es

Característica: La nota de voz del levantamiento no se pierde
  El recorrido con el cliente se hace caminando y dura poco: quien cotiza no
  alcanza a escribir, así que dicta. Esa nota de voz es, muchas veces, el único
  registro de lo que se vio en planta, y no se puede volver a grabar — el
  cliente ya no está.

  El sistema hace dos cosas con ella, y son dos cosas distintas: primero pasa la
  voz a texto, y después intenta ordenar ese texto en las tablas del formulario
  (materiales, personal, herramienta). La segunda puede salir mal sin que la
  primera lo haya hecho, y entonces el texto sigue siendo bueno: se enseña, y
  quien cotiza lo acomoda a mano.

  Mientras las dos se trataron como una sola, un tropiezo del que ordena tiraba
  el dictado completo. La persona veía un aviso rojo, ni una palabra de lo que
  acababa de decir, y nada que volver a grabar.

  Escenario: Lo que se dicta llega a la descripción del trabajo
    Dado que en el levantamiento se dictó "Cambiar el tablero de la nave dos"
    Cuando se manda la nota de voz al formulario
    Entonces la descripción del trabajo recibe "Cambiar el tablero de la nave dos"
    Y no se avisa de ninguna falla

  Escenario: El dictado se conserva aunque no se pueda ordenar la información
    Dado que en el levantamiento se dictó "Cambiar el tablero de la nave dos"
    Y que el asistente que ordena la información está fuera de servicio
    Cuando se manda la nota de voz al formulario
    Entonces la descripción del trabajo recibe "Cambiar el tablero de la nave dos"
    Y se avisa de que la información no se pudo ordenar

  Escenario: Una nota que menciona un error no se confunde con una falla
    Dado que en el levantamiento se dictó "Error del operador al medir, se repite"
    Cuando se manda la nota de voz al formulario
    Entonces la descripción del trabajo recibe "Error del operador al medir, se repite"
    Y no se avisa de ninguna falla

  Escenario: Si no se entendió nada, se dice
    Dado que en el levantamiento no se alcanzó a oír nada
    Cuando se manda la nota de voz al formulario
    Entonces la descripción del trabajo se queda vacía
    Y se avisa de que hay que revisar el micrófono
