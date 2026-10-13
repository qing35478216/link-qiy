from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.app import App
from ...types import Response


def _get_kwargs(
    app_id: str,
    *,
    body: App,
    x_tenant_id: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    headers["X-Tenant-Id"] = x_tenant_id

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/apps/{app_id}".format(
            app_id=quote(str(app_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> App | None:
    if response.status_code == 200:
        response_200 = App.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[App]:
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
    body: App,
    x_tenant_id: str,
) -> Response[App]:
    """更新应用基础信息

    Args:
        app_id (str):
        x_tenant_id (str):
        body (App):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[App]
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
    body: App,
    x_tenant_id: str,
) -> App | None:
    """更新应用基础信息

    Args:
        app_id (str):
        x_tenant_id (str):
        body (App):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        App
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
    body: App,
    x_tenant_id: str,
) -> Response[App]:
    """更新应用基础信息

    Args:
        app_id (str):
        x_tenant_id (str):
        body (App):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[App]
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
    body: App,
    x_tenant_id: str,
) -> App | None:
    """更新应用基础信息

    Args:
        app_id (str):
        x_tenant_id (str):
        body (App):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        App
    """

    return (
        await asyncio_detailed(
            app_id=app_id,
            client=client,
            body=body,
            x_tenant_id=x_tenant_id,
        )
    ).parsed
