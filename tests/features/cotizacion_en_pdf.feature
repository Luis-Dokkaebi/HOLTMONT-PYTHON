# language: es

Característica: La cotización se archiva en PDF con la línea del tracker
  Todo lo que se captura en una Pre Work Order —materiales, herramientas, mano
  de obra, equipo, programa y totales— se reparte al guardar entre cinco tablas
  hijas, y ninguna pantalla las vuelve a juntar. Quien abre la línea del tracker
  ve la tarea, no la cotización que la originó.

  La regla es que al guardar la orden su cotización quede como PDF entre los
  documentos de esa línea —la columna CARPETA, la del icono de nube—, de modo
  que quien ejecute el trabajo abra desde ahí lo que se cotizó, con los mismos
  números y sin depender de que alguien se acuerde de adjuntarlo.

  El PDF se **suma** a los documentos que ya tenía la orden. Sustituirlos
  borraría lo que subió una persona, que es exactamente la pérdida de
  información que esta regla quiere evitar.

  Escenario: La cotización queda entre los documentos de la línea
    Dado una Pre Work Order de "ACME INDUSTRIAL" con su estimación capturada
    Cuando se guarda la orden
    Entonces la línea del tracker lleva la cotización en PDF entre sus documentos
    Y la tarea de cada responsable del programa también la lleva

  Escenario: El PDF no borra lo que subió una persona
    Dado una Pre Work Order de "ACME INDUSTRIAL" con su estimación capturada
    Y que la orden ya trae adjunta la cotización del cliente
    Cuando se guarda la orden
    Entonces la línea del tracker conserva la cotización del cliente
    Y la línea del tracker lleva la cotización en PDF entre sus documentos

  Escenario: Si el PDF no se puede archivar, la orden se guarda igual
    Dado una Pre Work Order de "ACME INDUSTRIAL" con su estimación capturada
    Y que el almacenamiento de archivos no está disponible
    Cuando se guarda la orden
    Entonces la orden queda guardada con su folio
    Y el aviso dice que la cotización en PDF no se archivó
