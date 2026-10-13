from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_wechat_qrcode_status_response_200 import GetWechatQrcodeStatusResponse200
from ...types import Response


def _get_kwargs(
    ticket: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/auth/wechat/qrcode/{ticket}".format(
            ticket=quote(str(ticket), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GetWechatQrcodeStatusResponse200 | None:
    if response.status_code == 200:
        response_200 = GetWechatQrcodeStatusResponse200.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[GetWechatQrcodeStatusResponse200]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    ticket: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[GetWechatQrcodeStatusResponse200]:
    """轮询扫码状态

    Args:
        ticket (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetWechatQrcodeStatusResponse200]
    """

    kwargs = _get_kwargs(
        ticket=ticket,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    ticket: str,
    *,
    client: AuthenticatedClient | Client,
) -> GetWechatQrcodeStatusResponse200 | None:
    """轮询扫码状态

    Args:
        ticket (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetWechatQrcodeStatusResponse200
    """

    return sync_detailed(
        ticket=ticket,
        client=client,
    ).parsed


async def asyncio_detailed(
    ticket: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[GetWechatQrcodeStatusResponse200]:
    """轮询扫码状态

    Args:
        ticket (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetWechatQrcodeStatusResponse200]
    """

    kwargs = _get_kwargs(
        ticket=ticket,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    ticket: str,
    *,
    client: AuthenticatedClient | Client,
) -> GetWechatQrcodeStatusResponse200 | None:
    """轮询扫码状态

    Args:
        ticket (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetWechatQrcodeStatusResponse200
    """

    return (
        await asyncio_detailed(
            ticket=ticket,
            client=client,
        )
    ).parsed
