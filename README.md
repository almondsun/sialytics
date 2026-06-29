# SIAlytics

[![CI](https://github.com/almondsun/sialytics/actions/workflows/ci.yml/badge.svg)](https://github.com/almondsun/sialytics/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

SIAlytics extrae localmente la historia académica que el Sistema de Información
Académica (SIA) muestra a un estudiante de la Universidad Nacional de Colombia y
genera un libro de Excel orientado al seguimiento de su carrera.

La autenticación ocurre manualmente en una ventana de Chromium. SIAlytics no solicita,
recibe ni almacena nombres de usuario, contraseñas, cookies ni estados de sesión.

> [!IMPORTANT]
> SIAlytics no es un servicio oficial de la Universidad Nacional de Colombia. El XLSX
> contiene información académica personal y no está cifrado; debe conservarse en una
> ubicación privada.

## Funcionalidad

- Extrae asignaturas, calificaciones, tipologías de créditos e indicadores reconocidos.
- Consolida modalidades del mismo período, por ejemplo, período ordinario y validación
  por suficiencia.
- Calcula PAPA, PAPPI y estadísticas por semestre con la información visible en SIA.
- Genera un resumen de carrera, una hoja por semestre, avance curricular e historial
  completo.
- Incluye gráficos de evolución académica, calificaciones y distribución de créditos.
- Cancela la exportación si no reconoce una estructura o no puede demostrar que una
  sección terminó de cargar.

El flujo completo fue validado el 28 de junio de 2026 contra una sesión real de SIA.
Como SIA utiliza Oracle ADF y puede cambiar sin aviso, una estructura nueva requiere una
actualización explícita del extractor antes de volver a exportar.

## Requisitos

- Python 3.11 o posterior.
- Acceso autorizado del estudiante a SIA.
- Chromium administrado por Playwright.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[notebook]'
python -m playwright install chromium
jupyter lab notebooks/sialytics.ipynb
```

No escriba credenciales en el notebook, variables de entorno, archivos del proyecto ni
reportes de errores.

## Uso

1. Ejecute las dos celdas de código del notebook.
2. Autentíquese manualmente en la ventana de Chromium.
3. Espere el regreso automático a SIA.
4. Seleccione uno de los programas académicos detectados.
5. Espere la validación y la creación de `outputs/sialytics-<fecha>.xlsx`.

La carpeta de salida se resuelve desde la raíz del proyecto, incluso cuando Jupyter se
inicia desde `notebooks/`.

### Contenido del libro

- `Resumen`: PAPA, PAPPI, indicadores de SIA, avance general y tendencias por semestre.
- Una hoja por semestre: PAPA al cierre, PAPPI, créditos, asignaturas aprobadas y no
  aprobadas, estadísticas de calificaciones y gráficos.
- `Avance curricular`: créditos exigidos, aprobados, pendientes, inscritos y cursados por
  tipología.
- `Historial completo`: detalle consolidado de asignaturas y calificaciones.

La historia académica no publica días, horas ni aulas. Por esta razón, SIAlytics no
infiere ni genera una cuadrícula de horario semanal.

## Cálculos académicos

SIAlytics utiliza la terminología de SIA y presenta siempre **Calificación**.

- **PAPA:** promedio acumulado de las calificaciones numéricas, ponderadas por los
  créditos de cada asignatura.
- **PAPPI:** promedio ponderado del período académico correspondiente. Las cancelaciones
  con pérdida de créditos se incluyen en el denominador, de acuerdo con la
  [definición publicada por la UNAL](http://dama.manizales.unal.edu.co/index.php/promedios/).
- **Calificaciones cualitativas:** resultados como `APROBADA` cuentan en los totales de
  asignaturas, pero no se convierten artificialmente en una calificación numérica.

Los cálculos utilizan la precisión visible en la historia académica. Por ello, pueden
diferir ligeramente de un indicador oficial redondeado por SIA. Cuando SIA publica PAPA
o PAPPI explícitamente, el libro conserva ese valor oficial en el indicador correspondiente.

`No disponible` y `Sin información registrada` se reservan para ausencias mostradas
explícitamente por SIA. Una métrica calculada sin suficientes datos numéricos queda vacía;
no se presenta como una ausencia oficial.

## Seguridad y completitud

La navegación principal permite únicamente `sia.unal.edu.co` y el host institucional de
autenticación verificado `autenticasia.unal.edu.co`. Si el flujo institucional requiere
otros hosts, configure cada nombre exacto, separado por comas:

```bash
export SIALYTICS_AUTH_HOSTS='host-exacto-1.unal.edu.co,host-exacto-2.unal.edu.co'
```

Solo se aceptan `unal.edu.co` y sus subdominios; no se admiten URLs ni comodines. Aunque
un host esté autorizado para autenticación, SIAlytics solo extrae datos académicos desde
HTTPS en el host exacto `sia.unal.edu.co`.

Antes de exportar, cada sección debe:

- provenir del host académico autorizado;
- coincidir con una estructura conocida;
- haber cargado al menos una página;
- haber llegado inequívocamente al final de su paginación; y
- contener registros o una ausencia oficial reconocida.

Indicadores desconocidos, columnas modificadas, ciclos de paginación, sesiones expiradas
y secciones ambiguamente vacías cancelan la exportación. El libro se escribe primero en
un archivo temporal, se valida y luego se publica con permisos privados del usuario cuando
el sistema operativo lo permite.

## Desarrollo

Instale las dependencias de desarrollo y ejecute la validación completa:

```bash
python -m pip install -e '.[notebook,dev]'
python -m ruff format --check src tests
python -m ruff check .
python -m mypy
python -m pytest
python -m build
```

Las pruebas usan HTML sintético o sanitizado. No deben contener datos personales, cookies,
tokens, estados JSF ni respuestas autenticadas reales.

## Limitaciones

- El contrato del extractor corresponde al perfil observado de `Mi historia académica`.
- No se conserva HTML autenticado; los diagnósticos se limitan a códigos y nombres de
  sección sin información académica personal.
- El XLSX tiene permisos privados cuando el sistema lo permite, pero no está cifrado con
  contraseña.
- SIAlytics no certifica PAPA, PAPPI ni ningún otro indicador académico.

## Licencia

Distribuido bajo la licencia MIT. Consulte [LICENSE](LICENSE).

Las contribuciones son bienvenidas. Consulte [CONTRIBUTING.md](CONTRIBUTING.md) y
[SECURITY.md](SECURITY.md) antes de enviar cambios o reportar vulnerabilidades.
