from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from auth.dependencies import get_current_user
from api.services.terms_acceptance_service import terms_acceptance_service
from config.legal_versions import CURRENT_TERMS_VERSION, CURRENT_PRIVACY_VERSION

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/terms/check")
async def check_terms_acceptance(current_user: dict = Depends(get_current_user)):
    """
    Check if the current user has accepted the latest terms
    
    Returns:
        Dict with acceptance status and version info
    """
    try:
        user_id = current_user.get("sub")  # Cognito user ID
        
        result = await terms_acceptance_service.check_user_acceptance(
            user_id=user_id,
            required_terms_version=CURRENT_TERMS_VERSION,
            required_privacy_version=CURRENT_PRIVACY_VERSION
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking terms acceptance: {str(e)}"
        )


@router.get("/terms/history")
async def get_acceptance_history(current_user: dict = Depends(get_current_user)):
    """
    Get terms acceptance history for the current user
    
    Returns:
        List of acceptance records
    """
    try:
        user_id = current_user.get("sub")
        
        history = await terms_acceptance_service.get_acceptance_history(
            user_id=user_id,
            limit=10
        )
        
        return {
            "history": [record.dict() for record in history],
            "current_terms_version": CURRENT_TERMS_VERSION,
            "current_privacy_version": CURRENT_PRIVACY_VERSION
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting acceptance history: {str(e)}"
        )


@router.get("/versions")
async def get_current_versions():
    """
    Get current legal document versions
    
    Returns:
        Current version numbers
    """
    return {
        "terms_version": CURRENT_TERMS_VERSION,
        "privacy_version": CURRENT_PRIVACY_VERSION
    }