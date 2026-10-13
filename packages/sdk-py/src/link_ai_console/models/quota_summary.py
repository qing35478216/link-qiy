from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.quota_summary_plan import QuotaSummaryPlan
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.quota_summary_usage import QuotaSummaryUsage


T = TypeVar("T", bound="QuotaSummary")


@_attrs_define
class QuotaSummary:
    """
    Attributes:
        plan (QuotaSummaryPlan | Unset):
        plan_badge (str | Unset): 版本徽标文案
        wallet_balance (int | Unset): 积分余额
        upgrade_url (str | Unset):
        usage (QuotaSummaryUsage | Unset):
    """

    plan: QuotaSummaryPlan | Unset = UNSET
    plan_badge: str | Unset = UNSET
    wallet_balance: int | Unset = UNSET
    upgrade_url: str | Unset = UNSET
    usage: QuotaSummaryUsage | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        plan: str | Unset = UNSET
        if not isinstance(self.plan, Unset):
            plan = self.plan.value

        plan_badge = self.plan_badge

        wallet_balance = self.wallet_balance

        upgrade_url = self.upgrade_url

        usage: dict[str, Any] | Unset = UNSET
        if not isinstance(self.usage, Unset):
            usage = self.usage.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if plan is not UNSET:
            field_dict["plan"] = plan
        if plan_badge is not UNSET:
            field_dict["planBadge"] = plan_badge
        if wallet_balance is not UNSET:
            field_dict["walletBalance"] = wallet_balance
        if upgrade_url is not UNSET:
            field_dict["upgradeUrl"] = upgrade_url
        if usage is not UNSET:
            field_dict["usage"] = usage

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.quota_summary_usage import QuotaSummaryUsage  # noqa: PLC0415

        d = dict(src_dict)
        _plan = d.pop("plan", UNSET)
        plan: QuotaSummaryPlan | Unset
        if isinstance(_plan, Unset):
            plan = UNSET
        else:
            plan = QuotaSummaryPlan(_plan)

        plan_badge = d.pop("planBadge", UNSET)

        wallet_balance = d.pop("walletBalance", UNSET)

        upgrade_url = d.pop("upgradeUrl", UNSET)

        _usage = d.pop("usage", UNSET)
        usage: QuotaSummaryUsage | Unset
        if isinstance(_usage, Unset):
            usage = UNSET
        else:
            usage = QuotaSummaryUsage.from_dict(_usage)

        quota_summary = cls(
            plan=plan,
            plan_badge=plan_badge,
            wallet_balance=wallet_balance,
            upgrade_url=upgrade_url,
            usage=usage,
        )

        quota_summary.additional_properties = d
        return quota_summary

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
