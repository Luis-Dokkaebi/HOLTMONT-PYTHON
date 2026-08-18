# language: es

Característica: Solo se prospecta a quien se puede contactar
  El directorio del INEGI trae 20,957 negocios de la cadena de la construcción
  en la Ciudad de México, pero 7,885 de ellos no dejaron teléfono, ni correo, ni
  página. A esos no se les puede llamar ni escribir.

  Un negocio al que no hay forma de contactar no es un prospecto: es un punto en
  un mapa. La lista que recorre Compras solo ofrece a los contactables, y esa es
  la regla que este módulo tiene que respetar siempre.

  Escenario: La lista de prospectos deja fuera a quien no dejó cómo contactarlo
    Dado el directorio de negocios:
      | nombre                 | telefono   | correo         | pagina       | personal          |
      | FERRETERIA EL TORNILLO | 5512345678 |                |              | 0 a 5 personas    |
      | INGENIERIA DEL VALLE   |            | contacto@idv.mx|              | 11 a 30 personas  |
      | CONCRETOS ROMA         |            |                | www.croma.mx | 31 a 50 personas  |
      | TALLER SIN DATOS       |            |                |              | 0 a 5 personas    |
    Cuando Compras pide la lista de prospectos
    Entonces la lista trae 3 negocios
    Y "TALLER SIN DATOS" no aparece en la lista

  Escenario: Basta un solo dato de contacto para entrar a la lista
    Dado el directorio de negocios:
      | nombre                 | telefono   | correo         | pagina       | personal          |
      | FERRETERIA EL TORNILLO | 5512345678 |                |              | 0 a 5 personas    |
      | INGENIERIA DEL VALLE   |            | contacto@idv.mx|              | 11 a 30 personas  |
      | CONCRETOS ROMA         |            |                | www.croma.mx | 31 a 50 personas  |
    Cuando Compras pide la lista de prospectos
    Entonces "FERRETERIA EL TORNILLO" aparece en la lista
    Y "INGENIERIA DEL VALLE" aparece en la lista
    Y "CONCRETOS ROMA" aparece en la lista

  Escenario: Sin el candado de contacto el directorio se ve entero
    Dado el directorio de negocios:
      | nombre                 | telefono   | correo | pagina | personal       |
      | FERRETERIA EL TORNILLO | 5512345678 |        |        | 0 a 5 personas |
      | TALLER SIN DATOS       |            |        |        | 0 a 5 personas |
    Cuando se consulta el directorio completo
    Entonces la lista trae 2 negocios
    Y "TALLER SIN DATOS" aparece en la lista

  Escenario: Ser un negocio grande no sustituye al dato de contacto
    Dado el directorio de negocios:
      | nombre               | telefono   | correo | pagina | personal           |
      | CONSTRUCTORA GRANDE  |            |        |        | 251 y más personas |
      | HERRERIA CHICA       | 5555550001 |        |        | 0 a 5 personas     |
    Cuando Compras pide la lista de prospectos de 11 o más personas
    Entonces la lista trae 0 negocios
