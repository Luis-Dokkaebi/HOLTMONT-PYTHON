# language: es

Característica: Límite de uso cuando se desconecta la base de datos
  Para detener la plataforma, el dueño desconecta la base de datos del
  despliegue. Desde ese momento nadie puede trabajar con ella, y la
  plataforma tiene que decirlo con un aviso de límite de uso agotado por falta
  de espacio en la base de datos, tanto a quien ya tenía la sesión abierta
  como a quien intenta entrar.

  Escenario: Sin base de datos la plataforma muestra el aviso de límite de uso
    Dado que la plataforma no tiene base de datos conectada
    Cuando la plataforma revisa su estado
    Entonces el aviso dice "Límite de uso agotado por insuficiencia de espacio en base de datos. La plataforma detectó que el almacenamiento contratado ya no es suficiente para el volumen de datos del proyecto."

  Escenario: Sin base de datos nadie puede iniciar sesión
    Dado que la plataforma no tiene base de datos conectada
    Cuando alguien intenta iniciar sesión con su usuario y contraseña
    Entonces no entra
    Y se le muestra "Límite de uso agotado por insuficiencia de espacio en base de datos. La plataforma detectó que el almacenamiento contratado ya no es suficiente para el volumen de datos del proyecto."

  Escenario: Con la base de datos conectada no hay aviso
    Dado que la plataforma tiene la base de datos conectada
    Cuando la plataforma revisa su estado
    Entonces no se muestra ningún aviso
