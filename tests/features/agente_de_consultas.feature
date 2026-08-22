# language: es

Característica: El agente no manda datos de la empresa fuera del directorio
  El Agente de Consultas puede leer las tablas de actividades y de cotizaciones
  completas —el trabajo de todos los departamentos— y redactar correos con lo
  que encuentre. Eso lo hace útil y peligroso a partes iguales.

  El notebook del que salió mandaba el correo a cualquier dirección que se
  tecleara en la consola. Con eso, quien tenga el módulo puede sacar la
  información de la empresa a donde quiera, firmada con la cuenta de la empresa,
  y no queda registro de que haya pasado nada raro.

  La regla es que solo se escribe a gente del directorio. Si una dirección no
  está, no se manda ese correo **ni ningún otro del lote**, y se dice cuál fue:
  descartar la dirección en silencio dejaría a quien pulsó enviar creyendo que
  el reporte llegó completo.

  Escenario: Un correo a una dirección de fuera del directorio no sale
    Dado que el directorio de la empresa incluye "jaimeolivo@empresa.com"
    Y un borrador aprobado para el área "RH"
    Cuando se intenta mandarlo a "particular@gmail.com"
    Entonces no se manda ningún correo
    Y el motivo menciona "particular@gmail.com"

  Escenario: Un correo a una dirección del directorio sí sale
    Dado que el directorio de la empresa incluye "jaimeolivo@empresa.com"
    Y un borrador aprobado para el área "RH"
    Cuando se intenta mandarlo a "jaimeolivo@empresa.com"
    Entonces se manda 1 correo
    Y el correo llega a "jaimeolivo@empresa.com"

  Escenario: Una dirección de fuera en la copia frena el lote completo
    Dado que el directorio de la empresa incluye "jaimeolivo@empresa.com"
    Y un borrador aprobado para el área "RH"
    Cuando se intenta mandarlo a "jaimeolivo@empresa.com" con copia a "fuga@gmail.com"
    Entonces no se manda ningún correo
    Y el motivo menciona "fuga@gmail.com"

  Escenario: Sin correo configurado no se reporta un envío que no ocurrió
    Dado que el directorio de la empresa incluye "jaimeolivo@empresa.com"
    Y que el servidor de correo no está configurado
    Y un borrador aprobado para el área "RH"
    Cuando se intenta mandarlo a "jaimeolivo@empresa.com"
    Entonces no se manda ningún correo
    Y el motivo menciona "SMTP_HOST"
