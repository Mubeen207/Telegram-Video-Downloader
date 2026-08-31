import os
import json
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth

# Load environment variables
load_dotenv()

FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "maintainiq-e33d4")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")

# Initialize Firebase Admin
_firebase_initialized = False

def init_firebase_admin():
    global _firebase_initialized
    if _firebase_initialized or len(firebase_admin._apps) > 0:
        _firebase_initialized = True
        return

    try:
        # Check if FIREBASE_SERVICE_ACCOUNT is provided
        if FIREBASE_SERVICE_ACCOUNT:
            if os.path.exists(FIREBASE_SERVICE_ACCOUNT):
                # Path to JSON file
                cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
                firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
            else:
                # JSON content string
                service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        else:
            # Initialize with default options for project
            firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID})
        _firebase_initialized = True
    except Exception as e:
        # Avoid crashing app if admin creds are not yet set
        print(f"Warning: Firebase Admin initialization note: {e}")

init_firebase_admin()

security = HTTPBearer(auto_error=False)

async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Verifies Firebase ID token from Authorization header and returns user claims.
    """
    if not auth_header or not auth_header.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.credentials.strip()

    try:
        init_firebase_admin()
        decoded_token = auth.verify_id_token(token)
        return {
            "uid": decoded_token.get("uid"),
            "email": decoded_token.get("email"),
            "name": decoded_token.get("name", "User"),
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
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        # If running in local test environment without network reachability to Google auth certs
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
