from fastapi import APIRouter, Depends

from .. import db
from ..deps import require_token

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile")
def my_profile(token: dict = Depends(require_token)):
    """Return the admin-configured profile for the current key."""
    profile = db.get_full_profile(token["sub"])
    return profile or {}


@router.get("/features")
def my_features(token: dict = Depends(require_token)):
    """Return this user's feature flags."""
    return db.get_features(token["sub"])