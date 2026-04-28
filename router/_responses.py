from schema.response_schema import CommonResponse


# response models shared across routers, keyed by HTTP status code
COMMON_ERROR_RESPONSES = {
    401: {"description": "Unauthorized", "model": CommonResponse},
    403: {"description": "Forbidden", "model": CommonResponse},
    422: {"description": "Validation Error", "model": CommonResponse},
}

BAD_REQUEST_RESPONSE = {
    400: {"description": "Bad Request", "model": CommonResponse},
}


def not_found_response(resource: str) -> dict:
    """build a 404 response model with a resource-specific description"""
    return {404: {"description": f"{resource} not found", "model": CommonResponse}}
