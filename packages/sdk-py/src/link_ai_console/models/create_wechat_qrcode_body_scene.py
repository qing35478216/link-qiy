from enum import StrEnum


class CreateWechatQrcodeBodyScene(StrEnum):
    BIND = "bind"
    LOGIN = "login"

    def __str__(self) -> str:
        return str(self.value)
