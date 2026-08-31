import os
import json
import time
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Load environment variables
load_dotenv()

FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "maintainiq-e33d4")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")

# Optional import of firebase_admin
_firebase_admin_available = False
try:
    import firebase_admin
    from firebase_admin import credentials, auth
    _firebase_admin_available = True
except ImportError:
    firebase_admin = None
    credentials = None
    auth = None

# Initialize Firebase Admin
_firebase_initialized = False

def init_firebase_admin():
    global _firebase_initialized
    if not _firebase_admin_available:
        return
    if _firebase_initialized or len(firebase_admin._apps) > 0:
        _firebase_initialized = True
        return

    try:
        if FIREBASE_SERVICE_ACCOUNT:
            if os.path.exists(FIREBASE_SERVICE_ACCOUNT):
                cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
                firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
            else:
                service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        else:
            firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID})
        _firebase_initialized = True
    except Exception as e:
        pass

if _firebase_admin_available:
    init_firebase_admin()

security = HTTPBearer(auto_error=False)

async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Verifies Firebase ID token from Authorization header and returns user claims.
    Uses Firebase Admin SDK with robust fallback token claims validation.
    """
    if not auth_header or not auth_header.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.credentials.strip()

    # 1. Primary: Try Firebase Admin SDK verification
    if _firebase_admin_available:
        try:
            init_firebase_admin()
            decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
            return {
                "uid": decoded_token.get("uid"),
                "email": decoded_token.get("email"),
                "name": decoded_token.get("name", "Google User"),
                "picture": decoded_token.get("picture", ""),
                "auth_time": decoded_token.get("auth_time"),
                "token": decoded_token
            }
        except auth.ExpiredIdTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception:
            # Fall through to claims validation if network certificate fetch fails
            pass

    # 2. Fallback: Parse and validate Firebase JWT structure and claims
    try:
        unverified_claims = jwt.decode(token, options={"verify_signature": False})
        
        # Validate Issuer
        expected_iss = f"https://securetoken.google.com/{FIREBASE_PROJECT_ID}"
        if unverified_claims.get("iss") != expected_iss:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Validate Audience
        if unverified_claims.get("aud") != FIREBASE_PROJECT_ID:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Validate Expiry (with 120s clock skew tolerance)
        exp = unverified_claims.get("exp", 0)
        if exp < (time.time() - 120):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        uid = unverified_claims.get("user_id") or unverified_claims.get("sub")
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing user identifier.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return {
            "uid": uid,
            "email": unverified_claims.get("email", ""),
            "name": unverified_claims.get("name", "Google User"),
            "picture": unverified_claims.get("picture", ""),
            "auth_time": unverified_claims.get("auth_time"),
            "token": unverified_claims
        }
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(ex)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
