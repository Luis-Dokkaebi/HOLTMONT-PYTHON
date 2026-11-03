# language: es

Característica: Límite de uso cuando se desconecta la base de datos
  Para detener la plataforma, el dueño desconecta la base de datos del
  despliegue. Desde ese momento nadie puede trabajar con ella, y la
  plataforma tiene que decirlo con un aviso que explica que se está extendiendo
  la infraestructura de la base de datos, tanto a quien ya tenía la sesión
  abierta como a quien intenta entrar.

  Escenario: Sin base de datos la plataforma muestra el aviso
    Dado que la plataforma no tiene base de datos conectada
    Cuando la plataforma revisa su estado
    Entonces el aviso dice "Se requiere extender los módulos de la infraestructura de la base de datos debido a que se debe sostener la arquitectura premium de almacenar y asegurar el performance, disponibilidad, seguridad, backup, observabilidad y gobernanza de datos para Holtzar."

  Escenario: Sin base de datos nadie puede iniciar sesión
    Dado que la plataforma no tiene base de datos conectada
    Cuando alguien intenta iniciar sesión con su usuario y contraseña
    Entonces no entra
    Y se le muestra "Se requiere extender los módulos de la infraestructura de la base de datos debido a que se debe sostener la arquitectura premium de almacenar y asegurar el performance, disponibilidad, seguridad, backup, observabilidad y gobernanza de datos para Holtzar."

  Escenario: Sin base de datos no se puede guardar nada
    Dado que la plataforma no tiene base de datos conectada
    Cuando alguien con la sesión abierta intenta guardar una actividad del tracker
    Entonces no se guarda
    Y se le muestra "Se requiere extender los módulos de la infraestructura de la base de datos debido a que se debe sostener la arquitectura premium de almacenar y asegurar el performance, disponibilidad, seguridad, backup, observabilidad y gobernanza de datos para Holtzar."

  Escenario: Con la base de datos conectada no hay aviso
    Dado que la plataforma tiene la base de datos conectada
    Cuando la plataforma revisa su estado
    Entonces no se muestra ningún aviso
