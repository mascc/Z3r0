from fastapi import APIRouter, Query, WebSocket

from handler.agent_session_handler import (
    create_agent_session_handler,
    delete_agent_session_handler,
    handle_agent_stream,
    list_agent_events_handler,
    list_agent_sessions_handler,
)
from middleware.auth import auth_whitelist
from router._responses import COMMON_ERROR_RESPONSES, not_found_response
from schema.agent_session_schema import (
    CreateAgentSessionResponse,
    ListAgentEventsResponse,
    ListAgentSessionsResponse,
)
from schema.response_schema import CommonResponse


router = APIRouter(prefix="/agent-sessions", tags=["agent-sessions"])


async def create_agent_session_route() -> CommonResponse[CreateAgentSessionResponse]:
    """allocate a fresh server-generated session_id"""
    return await create_agent_session_handler()


async def list_agent_sessions_route(
    limit: int = Query(default=100),
) -> CommonResponse[ListAgentSessionsResponse]:
    """list recent agent sessions"""
    return await list_agent_sessions_handler(limit=limit)


async def list_agent_events_route(session_id: str) -> CommonResponse[ListAgentEventsResponse]:
    """replay the unified event stream of an agent session"""
    return await list_agent_events_handler(session_id=session_id)


async def delete_agent_session_route(session_id: str) -> CommonResponse:
    """delete an agent session and its SDK history"""
    return await delete_agent_session_handler(session_id=session_id)


router.add_api_route(
    "",
    list_agent_sessions_route,
    methods=["GET"],
    response_model=CommonResponse[ListAgentSessionsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "",
    create_agent_session_route,
    methods=["POST"],
    response_model=CommonResponse[CreateAgentSessionResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{session_id}/events",
    list_agent_events_route,
    methods=["GET"],
    response_model=CommonResponse[ListAgentEventsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{session_id}",
    delete_agent_session_route,
    methods=["DELETE"],
    response_model=CommonResponse,
    responses={**COMMON_ERROR_RESPONSES, **not_found_response("Agent session")},
)


# browsers cannot attach Authorization headers to WS handshakes — auth comes
# via query token, and auth_whitelist skips http auth middleware on upgrade
@router.websocket("/{session_id}/stream")
@auth_whitelist
async def agent_session_stream(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=""),
) -> None:
    await handle_agent_stream(websocket=websocket, session_id=session_id, token=token)
