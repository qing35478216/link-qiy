from enum import StrEnum


class SendSmsCodeBodyScene(StrEnum):
    BIND = "bind"
    LOGIN = "login"

    def __str__(self) -> str:
        return str(self.value)
