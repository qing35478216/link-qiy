from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.snapshot_app_config_response_201 import SnapshotAppConfigResponse201
from ...types import Response


def _get_kwargs(
    app_id: str,
    *,
    x_tenant_id: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    headers["X-Tenant-Id"] = x_tenant_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/apps/{app_id}/versions".format(
            app_id=quote(str(app_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> SnapshotAppConfigResponse201 | None:
    if response.status_code == 201:
        response_201 = SnapshotAppConfigResponse201.from_dict(response.json())

        return response_201

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[SnapshotAppConfigResponse201]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    app_id: str,
    *,
    client: AuthenticatedClient,
    x_tenant_id: str,
) -> Response[SnapshotAppConfigResponse201]:
    """手动创建配置快照

    Args:
        app_id (str):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SnapshotAppConfigResponse201]
    """

    kwargs = _get_kwargs(
        app_id=app_id,
        x_tenant_id=x_tenant_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    app_id: str,
    *,
    client: AuthenticatedClient,
    x_tenant_id: str,
) -> SnapshotAppConfigResponse201 | None:
    """手动创建配置快照

    Args:
        app_id (str):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SnapshotAppConfigResponse201
    """

    return sync_detailed(
        app_id=app_id,
        client=client,
        x_tenant_id=x_tenant_id,
    ).parsed


async def asyncio_detailed(
    app_id: str,
    *,
    client: AuthenticatedClient,
    x_tenant_id: str,
) -> Response[SnapshotAppConfigResponse201]:
    """手动创建配置快照

    Args:
        app_id (str):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SnapshotAppConfigResponse201]
    """

    kwargs = _get_kwargs(
        app_id=app_id,
        x_tenant_id=x_tenant_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    app_id: str,
    *,
    client: AuthenticatedClient,
    x_tenant_id: str,
) -> SnapshotAppConfigResponse201 | None:
    """手动创建配置快照

    Args:
        app_id (str):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SnapshotAppConfigResponse201
    """

    return (
        await asyncio_detailed(
            app_id=app_id,
            client=client,
            x_tenant_id=x_tenant_id,
        )
    ).parsed
