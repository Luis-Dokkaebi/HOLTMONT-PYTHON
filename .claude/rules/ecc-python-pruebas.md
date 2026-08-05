---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Testing

> Importado de ECC (rules/python/testing.md). El `common/testing.md` de ECC NO se importó: fija 80% de cobertura y contradice el piso medido de RESTRICCIONES_EXTREMAS.md §4, que es el que manda.

## Framework

Use **pytest** as the testing framework.

## Coverage

```bash
pytest --cov=src --cov-report=term-missing
```

## Test Organization

Use `pytest.mark` for test categorization:

```python
import pytest

@pytest.mark.unit
def test_calculate_total():
    ...

@pytest.mark.integration
def test_database_connection():
    ...
```

## Reference

See skill: `python-testing` for detailed pytest patterns and fixtures.
