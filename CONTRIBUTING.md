# Contribuir a SIAlytics

Gracias por contribuir. Los cambios deben preservar la privacidad del estudiante, la
completitud de la extracción y la terminología académica de la Universidad Nacional de
Colombia.

## Preparación

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[notebook,dev]'
python -m playwright install chromium
```

## Flujo de trabajo

1. Cree una rama corta desde `main`.
2. Mantenga el cambio limitado a un objetivo verificable.
3. Añada o actualice pruebas para todo cambio de comportamiento.
4. Ejecute la validación local completa.
5. Abra un pull request con el motivo, impacto y evidencia de validación.

```bash
python -m ruff format --check src tests
python -m ruff check .
python -m mypy
python -m pytest
python -m build
```

## Datos y seguridad

- Nunca incluya credenciales, cookies, tokens, estados JSF ni respuestas autenticadas.
- No adjunte XLSX, ODS, HTML, capturas o logs con información académica personal.
- Use únicamente fixtures sintéticos o completamente sanitizados.
- No debilite la lista de dominios permitidos ni las comprobaciones de completitud para
  hacer pasar una prueba.
- Los cambios en autenticación, navegación, parseo o exportación requieren pruebas de
  regresión específicas.

## Estilo

- Use nombres de archivos, carpetas, módulos y símbolos en inglés.
- Use terminología oficial de la UNAL en interfaces y documentación orientadas al
  estudiante.
- Evite abstracciones que no reduzcan acoplamiento o mejoren la verificabilidad.

Al participar, acepta cumplir el [Código de conducta](CODE_OF_CONDUCT.md).
