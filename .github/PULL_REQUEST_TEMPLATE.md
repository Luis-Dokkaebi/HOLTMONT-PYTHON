## Qué cambia y por qué

<!-- Una o dos frases. El "cómo" está en el diff. -->

## Control de calidad (obligatorio, en español y con especificidad)

Ver ejemplos de respuestas aceptables y no aceptables en
[`RESTRICCIONES_EXTREMAS.md`](../RESTRICCIONES_EXTREMAS.md) §R6.1.
**Una respuesta vacía o genérica invalida el PR.**

1. **¿Tiene un feedback loop que verifique el código generado?**
   -

2. **¿Cómo se hace el rollback si falla?**
   -

3. **¿Tiene observabilidad en producción?**
   -

4. **¿Escala si el equipo crece?**
   -

5. **¿Tu equipo lo mantiene sin ti?**
   -

## Restricciones extremas

Ver [`RESTRICCIONES_EXTREMAS.md`](../RESTRICCIONES_EXTREMAS.md).

- [ ] **R1** · `pytest` y `node tests/gas/run_tests.js` en verde
- [ ] **R2** · Escenario Gherkin para toda regla de negocio nueva o modificada
- [ ] **R3** · Cobertura del diff ≥ 90%; el global no bajó
- [ ] **R4** · Sin mutantes sobrevivientes nuevos en el núcleo
- [ ] **R5** · `ruff`, `radon`, `mypy` limpios en lo tocado; la complejidad no subió
- [ ] **R6** · PR con un solo propósito, ≤ 400 líneas útiles
- [ ] **R7** · Sin secretos; ninguna prueba toca la base de producción
- [ ] **R8** · Suite corrida 3 veces seguidas sin intermitencias
- [ ] **R9** · Contratos entre capas verificados
- [ ] **R10** · Rollback declarado y viable

## Directiva Cero

- [ ] **Este PR no modifica ningún umbral, configuración de CI ni `pytest.ini`, ni añade
      `skip` / `noqa` / `pragma: no cover` / `--no-verify` para que algo pase.**

<!-- Si tuviste que tocar una puerta, NO lo incluyas aquí: abre un PR aparte,
     sin código, explicando por qué la puerta está mal calibrada. -->

## Evidencia

<!-- Pega la salida real de ./run_tests.sh y del reporte de cobertura. -->

```
```
