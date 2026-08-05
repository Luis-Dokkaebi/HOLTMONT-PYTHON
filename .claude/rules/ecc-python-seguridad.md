---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Security

> Importado de ECC (rules/python/security.md). Complementa `.claude/rules/ecc-seguridad-comun.md` y R7 de RESTRICCIONES_EXTREMAS.md.

## Secret Management

```python
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ["OPENAI_API_KEY"]  # Raises KeyError if missing
```

## Security Scanning

- Use **bandit** for static security analysis:
  ```bash
  bandit -r src/
  ```

## Reference

See skill: `django-security` for Django-specific security guidelines (if applicable).
