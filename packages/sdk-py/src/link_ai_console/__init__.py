"""A client library for accessing LinkAI Console API（管理面）"""

from .client import AuthenticatedClient, Client

__all__ = (
    "AuthenticatedClient",
    "Client",
)
