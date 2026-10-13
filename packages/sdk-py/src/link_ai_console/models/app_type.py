from enum import StrEnum


class AppType(StrEnum):
    KNOWLEDGE = "knowledge"
    LIGHTWEIGHT = "lightweight"

    def __str__(self) -> str:
        return str(self.value)
