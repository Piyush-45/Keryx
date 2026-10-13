from typing import Annotated, Any

from fastapi import APIRouter, Body
from pydantic import BaseModel

from vp_shared.agent_config import validate_agent_config

router = APIRouter(prefix="/agent-configs", tags=["agent-configs"])


class ValidationIssue(BaseModel):
    path: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationIssue]


@router.post("/validate")
async def validate(config: Annotated[Any, Body()]) -> ValidationResult:
    """Validate an agent config. The dashboard's only validator; it never reimplements this in TS.

    Stateless and touches no tenant data. Moves behind auth when auth lands (Phase 3).
    """
    errors = validate_agent_config(config)
    return ValidationResult(
        valid=not errors,
        errors=[ValidationIssue(path=e.path, message=e.message) for e in errors],
    )
