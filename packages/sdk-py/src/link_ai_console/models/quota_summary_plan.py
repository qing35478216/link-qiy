from enum import StrEnum


class QuotaSummaryPlan(StrEnum):
    BASIC = "basic"
    ENTERPRISE = "enterprise"
    PRO = "pro"
    STANDARD = "standard"

    def __str__(self) -> str:
        return str(self.value)
