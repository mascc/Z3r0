from fastapi import APIRouter, Depends, Query, WebSocket

from handler.agent_session_handler import (
    create_agent_session_handler,
    delete_agent_session_handler,
    handle_agent_stream,
    list_agent_events_handler,
    list_agent_sessions_handler,
)
from middleware.auth import AuthUser, require_user
from router._responses import COMMON_ERROR_RESPONSES, not_found_response
from schema.agent_session_schema import (
    CreateAgentSessionResponse,
    ListAgentEventsResponse,
    ListAgentSessionsResponse,
)
from schema.response_schema import CommonResponse


# the websocket route does its own token check because browsers cannot attach
# Authorization headers to ws upgrades, so http auth is added per-route here
# rather than at router scope
router = APIRouter(prefix="/agent-sessions", tags=["agent-sessions"])

async def list_agent_sessions_route(
    limit: int = Query(default=100, ge=1, le=100),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ListAgentSessionsResponse]:
    return await list_agent_sessions_handler(limit=limit, user=user)


async def create_agent_session_route(
    user: AuthUser = Depends(require_user),
) -> CommonResponse[CreateAgentSessionResponse]:
    return await create_agent_session_handler(user=user)


async def delete_agent_session_route(
    session_id: str,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await delete_agent_session_handler(session_id=session_id, user=user)


async def list_agent_events_route(
    session_id: str,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ListAgentEventsResponse]:
    return await list_agent_events_handler(session_id=session_id, user=user)


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


@router.websocket("/{session_id}/stream")
async def agent_session_stream(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=""),
) -> None:
    await handle_agent_stream(websocket=websocket, session_id=session_id, token=token)
