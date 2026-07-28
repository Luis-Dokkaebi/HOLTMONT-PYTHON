"""
Modelos declarativos de SQLAlchemy.

Está vacío a propósito y con fecha de caducidad.

`SqlAlchemyEngine` **refleja** las tablas desde la base (`autoload_with`) en vez
de declararlas aquí. La razón es que el esquema no está versionado en el repo:
`migration/schema.sql` nunca existió (§1.1) y desde el entorno de desarrollo no
hay TCP al 5432 para hacer un `pg_dump`. Escribir a mano un
`Table("tasks", …)` con 28 columnas cuyos tipos no se pueden comprobar
produciría una declaración que parece autoridad y no lo es: el primer tipo mal
puesto se descubriría en producción.

Qué falta para llenar esto:

  1. Correr `scripts/verificar_base_tasks.py` con credenciales, que imprime los
     tipos reales de las columnas deducidas sin evidencia (`folio_sintetico`,
     `correo`, `hora_alta`, `hora_estimada_fin`).
  2. Versionar el DDL (`pg_dump --schema-only`) en `migration/schema.sql`.
  3. Declarar aquí los modelos a partir de ese DDL y retirar la reflexión, que
     cuesta una consulta por tabla en el primer uso de cada proceso.

Mientras tanto el contrato de tipos vive en `backend/schemas/task.py`, que es
donde de verdad se aplica: la frontera con el cliente.
"""
