from enum import StrEnum


class ListAppsType(StrEnum):
    ALL = "all"
    KNOWLEDGE = "knowledge"
    LIGHTWEIGHT = "lightweight"

    def __str__(self) -> str:
        return str(self.value)
