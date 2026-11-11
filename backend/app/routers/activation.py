from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class ActivateRequest(BaseModel):
    key: str
    fingerprint: str


class ActivateResponse(BaseModel):
    token: str


class ValidateRequest(BaseModel):
    token: str


class ValidateResponse(BaseModel):
    valid: bool


@router.post("/activate", response_model=ActivateResponse)
def activate(req: ActivateRequest):
    token, err = auth.activate(req.key, req.fingerprint)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"token": token}


@router.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest):
    ok, _ = auth.validate(req.token)
    return {"valid": ok}