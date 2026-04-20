"""Harness API entrypoints backed by the new pi_harness runtime."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.pi_harness import create_router

router = APIRouter()
router.include_router(create_router(prefix="/api/harness", tags=["harness"]))
router.include_router(create_router(prefix="/api/pi_harness", tags=["pi_harness"]))
