from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.app_config import AppConfig
from ...models.put_app_config_response_200 import PutAppConfigResponse200
from ...types import Response


def _get_kwargs(
    app_id: str,
    *,
    body: AppConfig,
    x_tenant_id: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    headers["X-Tenant-Id"] = x_tenant_id

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/apps/{app_id}/config".format(
            app_id=quote(str(app_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> PutAppConfigResponse200 | None:
    if response.status_code == 200:
        response_200 = PutAppConfigResponse200.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[PutAppConfigResponse200]:
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
    body: AppConfig,
    x_tenant_id: str,
) -> Response[PutAppConfigResponse200]:
    """保存配置七件套（保存即新版本）

    Args:
        app_id (str):
        x_tenant_id (str):
        body (AppConfig): 配置七件套——全部段落透传至运行时（平台不预设最佳值）

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PutAppConfigResponse200]
    """

    kwargs = _get_kwargs(
        app_id=app_id,
        body=body,
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
    body: AppConfig,
    x_tenant_id: str,
) -> PutAppConfigResponse200 | None:
    """保存配置七件套（保存即新版本）

    Args:
        app_id (str):
        x_tenant_id (str):
        body (AppConfig): 配置七件套——全部段落透传至运行时（平台不预设最佳值）

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PutAppConfigResponse200
    """

    return sync_detailed(
        app_id=app_id,
        client=client,
        body=body,
        x_tenant_id=x_tenant_id,
    ).parsed


async def asyncio_detailed(
    app_id: str,
    *,
    client: AuthenticatedClient,
    body: AppConfig,
    x_tenant_id: str,
) -> Response[PutAppConfigResponse200]:
    """保存配置七件套（保存即新版本）

    Args:
        app_id (str):
        x_tenant_id (str):
        body (AppConfig): 配置七件套——全部段落透传至运行时（平台不预设最佳值）

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PutAppConfigResponse200]
    """

    kwargs = _get_kwargs(
        app_id=app_id,
        body=body,
        x_tenant_id=x_tenant_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    app_id: str,
    *,
    client: AuthenticatedClient,
    body: AppConfig,
    x_tenant_id: str,
) -> PutAppConfigResponse200 | None:
    """保存配置七件套（保存即新版本）

    Args:
        app_id (str):
        x_tenant_id (str):
        body (AppConfig): 配置七件套——全部段落透传至运行时（平台不预设最佳值）

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PutAppConfigResponse200
    """

    return (
        await asyncio_detailed(
            app_id=app_id,
            client=client,
            body=body,
            x_tenant_id=x_tenant_id,
        )
    ).parsed
