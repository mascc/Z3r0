from http import HTTPStatus

from model.sandbox_image_model import SandboxImage
from schema.response_schema import CommonResponse
from schema.sandbox_image_schema import (
    CreateSandboxImageRequest,
    DeleteSandboxImageResponse,
    QuerySandboxImagesResponse,
    SandboxImageSchema,
)
from service.sandbox_image_service import (
    cancel_sandbox_image_pull,
    create_sandbox_image,
    delete_sandbox_image,
    query_sandbox_images,
    retry_sandbox_image,
)


def _to_sandbox_image_schema(sandbox_image: SandboxImage) -> SandboxImageSchema:
    """convert database model to public sandbox image schema"""
    return SandboxImageSchema.model_validate(sandbox_image)


async def create_sandbox_image_handler(request: CreateSandboxImageRequest) -> CommonResponse:
    """create sandbox image"""
    sandbox_image = await create_sandbox_image(image_name=request.image_name)
    return CommonResponse(
        message="docker pull started",
        data=_to_sandbox_image_schema(sandbox_image),
    )


async def delete_sandbox_image_handler(id: int) -> CommonResponse:
    """delete sandbox image"""
    deleted = await delete_sandbox_image(id)
    if not deleted:
        return CommonResponse(
            code=HTTPStatus.NOT_FOUND.value,
            message="sandbox image not found",
            data=DeleteSandboxImageResponse(id=id, deleted=False),
        )

    return CommonResponse(data=DeleteSandboxImageResponse(id=id, deleted=True))


async def cancel_sandbox_image_pull_handler(id: int) -> CommonResponse:
    """cancel active sandbox image pull"""
    sandbox_image, canceled = await cancel_sandbox_image_pull(id)
    if sandbox_image is None:
        return CommonResponse(
            code=HTTPStatus.NOT_FOUND.value,
            message="sandbox image not found",
        )
    if not canceled:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="only pulling sandbox images can be canceled",
            data=_to_sandbox_image_schema(sandbox_image),
        )

    return CommonResponse(
        message="docker pull canceled",
        data=_to_sandbox_image_schema(sandbox_image),
    )


async def retry_sandbox_image_handler(id: int) -> CommonResponse:
    """retry failed sandbox image pull"""
    sandbox_image, retried = await retry_sandbox_image(id)
    if sandbox_image is None:
        return CommonResponse(
            code=HTTPStatus.NOT_FOUND.value,
            message="sandbox image not found",
        )
    if not retried:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="only failed or canceled sandbox images can be retried",
            data=_to_sandbox_image_schema(sandbox_image),
        )

    return CommonResponse(
        message="docker pull restarted",
        data=_to_sandbox_image_schema(sandbox_image),
    )


async def query_sandbox_images_handler(page: int = 1, size: int = 100, keyword: str = "") -> CommonResponse:
    """query sandbox images"""
    if page < 1:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="page must be greater than or equal to 1",
        )
    if size < 1 or size > 100:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="size must be between 1 and 100",
        )

    sandbox_images = await query_sandbox_images(page=page, size=size, keyword=keyword)
    data = QuerySandboxImagesResponse(
        page=page,
        size=size,
        items=[_to_sandbox_image_schema(sandbox_image) for sandbox_image in sandbox_images],
    )
    return CommonResponse(data=data)
