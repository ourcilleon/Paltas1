# Plantilla de automatización en Python

Base pequeña, mantenible y lista para extender con archivos, APIs, correo,
Telegram u otros destinos. La CLI está separada de la lógica de negocio y el
modo `--dry-run` permite comprobar una ejecución sin realizar efectos externos.

## Requisitos

- Python 3.11 o superior

No hay dependencias de ejecución externas.

## Estructura

```text
python-automation-template/
├── src/automation/
│   ├── cli.py              # Traduce argumentos CLI a una llamada del servicio
│   ├── config.py           # Variables de entorno y validación
│   ├── errors.py           # Errores esperados de la aplicación
│   ├── logging_config.py   # Configuración central de logs
│   └── service.py          # Lógica de negocio y adaptador de archivo
├── tests/                  # Pruebas con unittest
├── .env.example
└── pyproject.toml
```

## Instalación

Desde esta carpeta:

```bash
python -m pip install -e .
cp .env.example .env
```

La instalación editable expone el comando `automation`.

## Configuración

La aplicación lee `.env` y respeta primero cualquier variable ya exportada por
el sistema:

| Variable | Valor por defecto | Uso |
| --- | --- | --- |
| `APP_ENV` | `development` | Nombre del entorno |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `OUTPUT_DIR` | `output` | Carpeta del resultado de ejemplo |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Timeout para futuros adaptadores externos |

No guardes credenciales en `.env.example` ni en el repositorio. Para futuros
servicios, añade solo nombres de variables y valores de muestra no sensibles.

## Ejecución

Simular sin escribir archivos:

```bash
automation --name "Ada" --dry-run
```

Ejecutar realmente:

```bash
automation --name "Ada"
cat output/result.txt
```

Usar otro archivo de configuración:

```bash
automation --name "Ada" --env-file .env.production --dry-run
```

También puede ejecutarse sin instalar, indicando la carpeta `src`:

```bash
PYTHONPATH=src python -m automation.cli --name "Ada" --dry-run
```

Los códigos de salida son `0` para éxito, `2` para errores esperados de entrada
o configuración, `130` para cancelación y `1` para fallos inesperados.

## Pruebas

No requieren paquetes adicionales:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Cómo extenderla

`AutomationService` depende del protocolo `TextDestination`, no de una
tecnología concreta. Para añadir una integración:

1. Crea un adaptador que implemente `send(content, *, dry_run)`.
2. En `dry_run=True`, devuelve una descripción sin llamar a redes ni modificar
   archivos.
3. Convierte errores técnicos a `ExternalOperationError`, conservando la causa.
4. Inyecta el adaptador en `AutomationService` desde la CLI.

Ejemplo conceptual:

```python
class TelegramDestination:
    def send(self, content: str, *, dry_run: bool) -> str:
        if dry_run:
            return f"Se enviaría un mensaje de {len(content)} caracteres"
        # Llamada real al cliente de Telegram.
        return "Mensaje enviado"
```

Esta separación permite mantener las reglas de negocio comprobables sin
argumentos CLI, red ni credenciales reales.