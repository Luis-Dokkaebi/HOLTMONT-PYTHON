# language: es

Característica: El apartado Dashboard Streamlit convierte un Excel en el dashboard de la liga corta
  Antonio Salazar arrastra su Excel al apartado, pulsa Procesar y, cuando el
  dashboard queda generado, recibe la liga corta de Streamlit. La liga es
  siempre la misma y enseña el último dashboard que pasó las pruebas.

  Escenario: Antonio Salazar tiene el apartado
    Dado que "ANTONIO_SALAZAR" entra al sistema
    Entonces ve el apartado "Dashboard Streamlit"

  Escenario: El resto del personal no tiene el apartado
    Dado que "TERESA_GARZA" entra al sistema
    Entonces no ve el apartado "Dashboard Streamlit"

  Escenario: El administrador no lo hereda por su rol
    Dado que "LUIS_CARLOS" entra al sistema
    Entonces no ve el apartado "Dashboard Streamlit"

  Escenario: Al terminar el procesamiento se entrega la liga corta
    Dado que la liga corta del dashboard está configurada
    Y que Antonio procesa "ST_B2C_OCR.xlsx"
    Cuando GitHub termina de generar el dashboard
    Entonces se avisa "Dashboard generado en GitHub."
    Y Antonio recibe la liga corta del dashboard

  Escenario: Un dashboard que no pasa las pruebas no cambia la liga
    Dado que la liga corta del dashboard está configurada
    Y que Antonio procesa "ST_B2C_OCR.xlsx"
    Cuando el dashboard nuevo no pasa las pruebas en GitHub
    Entonces se avisa que la liga sigue mostrando el dashboard anterior
