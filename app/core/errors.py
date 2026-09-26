"""Errores «de usuario»: llevan un mensaje en español y se devuelven como HTTP 400 (nunca un traceback)."""


class UserError(Exception):
    """Mensaje pensado para mostrarse tal cual en la interfaz."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
