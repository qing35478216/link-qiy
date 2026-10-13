from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.list_apps_type import ListAppsType
from ...models.page import Page
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    cursor: str | Unset = UNSET,
    limit: int | Unset = 20,
    type_: ListAppsType | Unset = UNSET,
    x_tenant_id: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    headers["X-Tenant-Id"] = x_tenant_id

    params: dict[str, Any] = {}

    params["cursor"] = cursor

    params["limit"] = limit

    json_type_: str | Unset = UNSET
    if not isinstance(type_, Unset):
        json_type_ = type_.value

    params["type"] = json_type_

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/apps",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Page | None:
    if response.status_code == 200:
        response_200 = Page.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Page]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    cursor: str | Unset = UNSET,
    limit: int | Unset = 20,
    type_: ListAppsType | Unset = UNSET,
    x_tenant_id: str,
) -> Response[Page]:
    """应用列表（cursor 分页）

    Args:
        cursor (str | Unset):
        limit (int | Unset):  Default: 20.
        type_ (ListAppsType | Unset):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Page]
    """

    kwargs = _get_kwargs(
        cursor=cursor,
        limit=limit,
        type_=type_,
        x_tenant_id=x_tenant_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    cursor: str | Unset = UNSET,
    limit: int | Unset = 20,
    type_: ListAppsType | Unset = UNSET,
    x_tenant_id: str,
) -> Page | None:
    """应用列表（cursor 分页）

    Args:
        cursor (str | Unset):
        limit (int | Unset):  Default: 20.
        type_ (ListAppsType | Unset):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Page
    """

    return sync_detailed(
        client=client,
        cursor=cursor,
        limit=limit,
        type_=type_,
        x_tenant_id=x_tenant_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    cursor: str | Unset = UNSET,
    limit: int | Unset = 20,
    type_: ListAppsType | Unset = UNSET,
    x_tenant_id: str,
) -> Response[Page]:
    """应用列表（cursor 分页）

    Args:
        cursor (str | Unset):
        limit (int | Unset):  Default: 20.
        type_ (ListAppsType | Unset):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Page]
    """

    kwargs = _get_kwargs(
        cursor=cursor,
        limit=limit,
        type_=type_,
        x_tenant_id=x_tenant_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    cursor: str | Unset = UNSET,
    limit: int | Unset = 20,
    type_: ListAppsType | Unset = UNSET,
    x_tenant_id: str,
) -> Page | None:
    """应用列表（cursor 分页）

    Args:
        cursor (str | Unset):
        limit (int | Unset):  Default: 20.
        type_ (ListAppsType | Unset):
        x_tenant_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Page
    """

    return (
        await asyncio_detailed(
            client=client,
            cursor=cursor,
            limit=limit,
            type_=type_,
            x_tenant_id=x_tenant_id,
        )
    ).parsed
