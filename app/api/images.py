"""Bounded multipart uploads for one image and its optional caption."""

import asyncio
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.routing import APIRoute
from openai import APITimeoutError, OpenAIError
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

from app.content.image_analysis import ImageAnalysisReport

_MAX_UPLOAD = 5 * 1024 * 1024
_MAX_REQUEST = _MAX_UPLOAD + 32 * 1024
_UPLOAD_TIMEOUT = 20
_MAX_PIXELS = 16_000_000
_MAX_SIDE = 2048
_FORMATS = ("PNG", "JPEG", "WEBP")


class ImageUploadRoute(APIRoute):
    def get_route_handler(self):
        route_handler = super().get_route_handler()

        async def handle(request: Request):
            analyzer = request.app.state.image_analyzer
            if analyzer is None:
                raise HTTPException(
                    503, "Image analysis is disabled. Enable it and configure OPENAI_API_KEY."
                )
            if (
                request.headers.get("content-type", "").partition(";")[0].strip().lower()
                != "multipart/form-data"
            ):
                raise HTTPException(415, "Upload one image as multipart/form-data.")
            if analyzer.slots.locked():
                raise HTTPException(429, "Image analysis is busy. Try again shortly.")

            received = 0
            deadline = asyncio.get_running_loop().time() + _UPLOAD_TIMEOUT

            async def receive():
                nonlocal received
                try:
                    async with asyncio.timeout_at(deadline):
                        event = await request.receive()
                except TimeoutError as exc:
                    raise HTTPException(408, "The image upload timed out.") from exc
                received += len(event.get("body", b""))
                if received > _MAX_REQUEST:
                    raise HTTPException(413, "Image upload exceeds 5 MiB.")
                return event

            async with analyzer.slots:
                return await route_handler(Request(request.scope, receive))

        return handle


router = APIRouter(prefix="/api/v1/images", tags=["Image analysis"], route_class=ImageUploadRoute)


def _prepare_image(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data), formats=_FORMATS) as image:
            if image.width * image.height > _MAX_PIXELS:
                raise HTTPException(413, "Use an image with at most 16 megapixels.")
            if getattr(image, "n_frames", 1) != 1:
                raise HTTPException(415, "Upload a still image.")
            oriented = ImageOps.exif_transpose(image)
            oriented.thumbnail((_MAX_SIDE, _MAX_SIDE), Image.Resampling.LANCZOS)
            rgba = oriented.convert("RGBA")
            clean = Image.new("RGB", rgba.size, "white")
            clean.paste(rgba, mask=rgba.getchannel("A"))
            output = BytesIO()
            clean.save(output, format="PNG")
            return output.getvalue()
    except Image.DecompressionBombError as exc:
        raise HTTPException(413, "Use an image with at most 16 megapixels.") from exc
    except (OSError, SyntaxError, ValueError) as exc:
        raise HTTPException(415, "Upload a readable PNG, JPEG or WebP image.") from exc


@router.post("/analyze", response_model=ImageAnalysisReport)
async def analyze_image(
    request: Request,
    image: Annotated[UploadFile, File(description="Still PNG, JPEG or WebP, up to 5 MiB and 16 MP")],
    caption: Annotated[
        str | None, Form(max_length=2000, description="Caption from the surrounding post")
    ] = None,
):
    data = await image.read(_MAX_UPLOAD + 1)
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, "Image upload exceeds 5 MiB.")
    if not data:
        raise HTTPException(422, "The image file is empty.")
    png = await run_in_threadpool(_prepare_image, data)
    try:
        return await request.app.state.image_analyzer.analyze(png, (caption or "").strip())
    except (TimeoutError, APITimeoutError) as exc:
        raise HTTPException(504, "Image analysis timed out. Try again.") from exc
    except (OpenAIError, ValueError) as exc:
        raise HTTPException(502, "The image model could not return a usable assessment.") from exc
