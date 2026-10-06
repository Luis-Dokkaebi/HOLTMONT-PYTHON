# language: es

Característica: El dashboard de la Pre Work Order se actualiza con cada documento
  Cuando el cotizador sube a la Pre Work Order un documento con datos, el
  dashboard se vuelve a generar con ese documento. La liga corta es siempre la
  misma y enseña el último dashboard que pasó las pruebas.

  Escenario: Subir una hoja de cálculo regenera el dashboard
    Dado que la liga corta del dashboard está configurada
    Cuando el cotizador sube "Junta HLT.xlsx" a la Pre Work Order
    Entonces se pide regenerar el dashboard con "Junta HLT.xlsx"
    Y el cotizador recibe la liga corta del dashboard

  Escenario: Una foto de la obra no reemplaza el dashboard
    Dado que la liga corta del dashboard está configurada
    Cuando el cotizador sube "fachada.jpg" a la Pre Work Order
    Entonces no se pide regenerar el dashboard

  Escenario: Un archivo que no es de Holtmont no se manda a generar
    Dado que la liga corta del dashboard está configurada
    Cuando alguien pide el dashboard de "https://otro-sitio.com/storage/v1/object/public/a/costos.xlsx"
    Entonces no se pide regenerar el dashboard

  Escenario: Un dashboard que no pasa las pruebas no se publica
    Dado que en la liga corta está publicado un dashboard que funciona
    Cuando el dashboard nuevo falla las pruebas en cada intento
    Entonces la liga corta sigue mostrando el dashboard anterior
    Y el intento queda registrado como cancelado
