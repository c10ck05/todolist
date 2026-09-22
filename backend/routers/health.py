"""Health-check endpoint."""

from fastapi import APIRouter
import os


router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok", "revision": os.getenv("RENDER_GIT_COMMIT", "local")}
