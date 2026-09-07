"""Excepciones controladas de la aplicación."""


class AutomationError(Exception):
    """Error esperado que puede mostrarse al usuario sin un traceback."""


class ConfigurationError(AutomationError):
    """La configuración no es válida o está incompleta."""


class ExternalOperationError(AutomationError):
    """Una operación con efectos externos no pudo completarse."""
