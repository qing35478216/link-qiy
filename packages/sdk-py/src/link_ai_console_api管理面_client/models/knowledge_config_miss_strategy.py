from enum import StrEnum


class KnowledgeConfigMissStrategy(StrEnum):
    FIXEDMESSAGE = "fixedMessage"
    FREE = "free"
    HUMANTRANSFER = "humanTransfer"

    def __str__(self) -> str:
        return str(self.value)
