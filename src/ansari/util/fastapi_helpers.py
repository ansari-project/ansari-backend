from fastapi import Depends, HTTPException, Request
from jwt import PyJWTError

from ansari.ansari_logger import get_logger
from ansari.config import Settings, get_settings

logger = get_logger()


# Defined in a separate file to avoid circular imports between main_*.py files
def validate_cors(request: Request, settings: Settings = Depends(get_settings)) -> bool:
    try:
        logger.debug(f"Headers of raw request are: {request.headers}")
        origins = get_settings().ORIGINS
        incoming_origin = [
            request.headers.get("origin", ""),  # If coming from ansari's frontend website
            request.headers.get("host", ""),  # If coming from Meta's WhatsApp API
        ]

        mobile = request.headers.get("x-mobile-ansari", "")
        if any(i_o in origins for i_o in incoming_origin) or mobile == "ANSARI":
            logger.debug("CORS OK")
            return True
        raise HTTPException(status_code=502, detail="Not Allowed Origin")
    except PyJWTError:
        raise HTTPException(status_code=403, detail="Could not validate credentials")
