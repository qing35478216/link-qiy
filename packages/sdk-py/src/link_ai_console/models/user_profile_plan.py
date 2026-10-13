from enum import StrEnum


class UserProfilePlan(StrEnum):
    BASIC = "basic"
    ENTERPRISE = "enterprise"
    PRO = "pro"
    STANDARD = "standard"

    def __str__(self) -> str:
        return str(self.value)
