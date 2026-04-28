import json
import sys
from pathlib import Path
from typing import Any


ROOT_PATH = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT_PATH / "web" / "openapi.json"


def export_openapi_schema() -> Path:
    """export fastapi openapi schema for frontend type generation"""
    if str(ROOT_PATH) not in sys.path:
        sys.path.insert(0, str(ROOT_PATH))

    from app import create_app

    app = create_app()
    schema = app.openapi()
    _patch_auth_contracts(app, schema)
    _patch_list_query_contracts(schema)
    _patch_validation_contracts(schema)
    _patch_error_contracts(schema)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return OUTPUT_PATH


def _patch_auth_contracts(app: Any, schema: dict[str, Any]) -> None:
    """add middleware-driven auth contracts to exported openapi schema"""
    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas.setdefault("CommonResponse_Any_", _common_response_any_schema())
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    for route in app.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        methods = getattr(route, "methods", None)
        if endpoint is None or not methods or path not in schema.get("paths", {}):
            continue

        is_whitelisted = bool(getattr(endpoint, "__auth_whitelist__", False))
        required_role = getattr(endpoint, "__auth_required_role__", None)
        for method in methods:
            method_name = method.lower()
            operation = schema["paths"][path].get(method_name)
            if operation is None:
                continue

            if not is_whitelisted:
                operation["security"] = [{"BearerAuth": []}]
                operation.setdefault("responses", {})["401"] = _common_response_ref(
                    "Unauthorized"
                )
            if required_role is not None:
                operation.setdefault("responses", {})["403"] = _common_response_ref(
                    "Forbidden"
                )


def _patch_validation_contracts(schema: dict[str, Any]) -> None:
    """replace FastAPI validation response docs with CommonResponse docs"""
    for methods in schema.get("paths", {}).values():
        for operation in methods.values():
            responses = operation.get("responses")
            if not isinstance(responses, dict) or "422" not in responses:
                continue
            _ensure_common_response(responses["422"], "Validation Error")


def _patch_error_contracts(schema: dict[str, Any]) -> None:
    """normalize documented error responses to the runtime CommonResponse shape"""
    descriptions = {
        "400": "Bad Request",
        "401": "Unauthorized",
        "403": "Forbidden",
        "404": "Not Found",
        "422": "Validation Error",
    }
    for methods in schema.get("paths", {}).values():
        for operation in methods.values():
            responses = operation.get("responses")
            if not isinstance(responses, dict):
                continue
            for status_code, description in descriptions.items():
                response = responses.get(status_code)
                if isinstance(response, dict):
                    _ensure_common_response(response, description)


def _patch_list_query_contracts(schema: dict[str, Any]) -> None:
    """document handler-level list query constraints that FastAPI cannot infer"""
    list_paths = ("/api/system-users", "/api/sandbox-images", "/api/work-projects")
    for path in list_paths:
        operation = schema.get("paths", {}).get(path, {}).get("get")
        if not isinstance(operation, dict):
            continue

        for parameter in operation.get("parameters", []):
            if not isinstance(parameter, dict):
                continue
            parameter_schema = parameter.get("schema")
            if not isinstance(parameter_schema, dict):
                continue
            if parameter.get("name") == "page":
                parameter_schema["minimum"] = 1
            if parameter.get("name") == "size":
                parameter_schema["minimum"] = 1
                parameter_schema["maximum"] = 100

        operation.setdefault("responses", {})["400"] = _common_response_ref("Bad Request")


def _common_response_ref(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {
                    "$ref": "#/components/schemas/CommonResponse_Any_",
                }
            }
        },
    }


def _ensure_common_response(response: dict[str, Any], description: str) -> None:
    response["description"] = response.get("description") or description
    content = response.setdefault("content", {})
    json_content = content.setdefault("application/json", {})
    json_content["schema"] = {"$ref": "#/components/schemas/CommonResponse_Any_"}


def _common_response_any_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "title": "CommonResponse[Any]",
        "properties": {
            "code": {
                "type": "integer",
                "title": "Code",
                "default": 200,
            },
            "message": {
                "type": "string",
                "title": "Message",
                "default": "success",
            },
            "data": {
                "title": "Data",
            },
        },
    }


if __name__ == "__main__":
    output_path = export_openapi_schema()
    print(f"OpenAPI schema exported to {output_path}")
