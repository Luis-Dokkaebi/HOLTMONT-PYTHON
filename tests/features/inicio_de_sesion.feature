# language: es

Característica: Inicio de sesión con contraseñas que llevan acentos o ñ
  Las contraseñas del personal se escriben en español. Una «ñ» o un acento,
  en la contraseña guardada o en la que se teclea, no puede impedir el acceso
  de quien la escribe bien, ni convertir un error de tecleo en un «Connection
  Error»: quien se equivoca tiene que ver que su contraseña es incorrecta.

  Escenario: Entra quien tiene una ñ en su contraseña y la escribe bien
    Dado que la cuenta "ROCIO_CASTRO" tiene la contraseña "Contraseña_Rocío"
    Cuando "ROCIO_CASTRO" inicia sesión con la contraseña "Contraseña_Rocío"
    Entonces entra al sistema

  Escenario: Quien teclea una ñ por error ve que la contraseña es incorrecta
    Dado que la cuenta "LUIS_CARLOS" tiene la contraseña "admin2025"
    Cuando "LUIS_CARLOS" inicia sesión con la contraseña "contraseña"
    Entonces no entra
    Y se le muestra "Usuario o contraseña incorrectos."
