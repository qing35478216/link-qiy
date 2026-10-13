from enum import StrEnum


class GetWechatQrcodeStatusResponse200Status(StrEnum):
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    PENDING = "pending"
    SCANNED = "scanned"

    def __str__(self) -> str:
        return str(self.value)
