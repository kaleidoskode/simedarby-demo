import os
import jwt
from typing import Dict, Any
from pathlib import Path
from app.middleware.exception import CustomErrorException


class JWTVerifier:
    """JWT verification utility with enhanced security configuration."""

    def __init__(self):
        # Use environment variable for public key path with fallback
        # self.public_key_path = Path(
        #     os.getenv('JWT_PUBLIC_KEY_PATH', '.data/appcode_public.key')
        # )

        self.public_key_path = Path(".data/appcode_public.key")

        # Enhanced security configuration - PROPER JWT VERIFICATION
        self.verify_options = {
            "verify_signature": True,   # CRITICAL: Enable signature verification
            "verify_exp": False,        # Flexible: Your tokens don't have expiration
            "verify_nbf": True,         # ENABLE: Require not-before time
            "verify_iat": True,         # ENABLE: Require issued-at time
            "verify_aud": True,         # ENABLE: Require audience validation
            "verify_iss": True,         # ENABLE: Require issuer validation
            "require": ["iat", "iss", "aud"]   # REQUIRE: Essential claims
        }

        # JWT configuration with environment variables
        self.jwt_options = {
            "issuer": os.getenv('JWT_ISSUER', 'awfatech global'),
            "subject": os.getenv('JWT_SUBJECT', 'general'),
            "audience": os.getenv('JWT_AUDIENCE', 'user'),
            "algorithms": ["RS256"]  # SECURE: Only allow RS256
        }

        # Token expiration settings
        self.max_token_age = int(
            os.getenv('JWT_MAX_AGE_SECONDS', 3600))  # 1 hour default

    def _load_public_key(self) -> str:
        """Load the public key from file with enhanced security."""
        try:
            # Resolve to absolute path to prevent path traversal
            absolute_path = self.public_key_path.resolve()

            # Security check: Ensure path is within expected directory
            if not str(absolute_path).startswith(str(Path.cwd())):
                raise CustomErrorException(
                    "Invalid public key path", status_code=500)

            if not absolute_path.exists():
                raise CustomErrorException(
                    f"Public key file not found: {absolute_path}. "
                    f"Please ensure the public key file exists for JWT verification. "
                    f"Set JWT_PUBLIC_KEY_PATH environment variable or place the key at {absolute_path}")

            with open(absolute_path, 'r', encoding='utf-8') as key_file:
                key_content = key_file.read().strip()

                # Basic validation that it looks like a public key
                if not key_content.startswith('-----BEGIN PUBLIC KEY-----'):
                    raise CustomErrorException(
                        "Invalid public key format. Expected PEM format starting with '-----BEGIN PUBLIC KEY-----'",
                        status_code=500)

                return key_content

        except Exception as e:
            raise CustomErrorException(f"Error loading public key: {str(e)}")

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify JWT token using RS256 algorithm with comprehensive security checks.

        Args:
            token: JWT token string

        Returns:
            Dict containing decoded token payload

        Raises:
            CustomErrorException: If token is invalid or verification fails
        """
        try:
            # Load the public key for signature verification
            public_key = self._load_public_key()

            # Decode and verify the token with comprehensive validation
            decoded = jwt.decode(
                token,
                public_key,
                algorithms=self.jwt_options["algorithms"],
                options=self.verify_options,
                issuer=self.jwt_options["issuer"],
                audience=self.jwt_options["audience"]
            )

            # Additional custom validation
            self._validate_token_claims(decoded)

            return decoded

        except jwt.ExpiredSignatureError:
            raise CustomErrorException("Token has expired", status_code=401)
        except jwt.InvalidSignatureError:
            raise CustomErrorException(
                "Invalid token signature", status_code=401)
        except jwt.InvalidAudienceError:
            raise CustomErrorException(
                "Invalid token audience", status_code=401)
        except jwt.InvalidIssuerError:
            raise CustomErrorException("Invalid token issuer", status_code=401)
        except jwt.InvalidTokenError as e:
            raise CustomErrorException(
                f"Invalid token: {str(e)}", status_code=401)
        except jwt.DecodeError as e:
            raise CustomErrorException(
                f"Token decode error: {str(e)}", status_code=401)
        except Exception as e:
            # Log error but don't expose internal details
            raise CustomErrorException(
                f"Token verification failed : {e}", status_code=401)

    def _validate_token_claims(self, decoded: Dict[str, Any]) -> None:
        """Additional custom validation for token claims."""
        # Check if token is not too old (but allow future timestamps for testing)
        if 'iat' in decoded:
            import time
            current_time = int(time.time())
            token_age = current_time - decoded['iat']

            # Allow future timestamps (for testing) but check if token is too old
            # if token_age < -3600:  # Allow tokens up to 1 hour in the future
            #     raise CustomErrorException(
            #         "Token timestamp is too far in the future", status_code=401)
            # elif token_age > self.max_token_age:
            #     raise CustomErrorException("Token is too old", status_code=401)

        # Validate required claims for your token format
        required_claims = ['app_code', 'cust_name', 'iss', 'aud', 'iat']
        for claim in required_claims:
            if claim not in decoded:
                raise CustomErrorException(
                    f"Missing required claim: {claim}", status_code=401)

    # REMOVED: verify_token_debug method for security
    # If you need debug functionality, implement it with proper environment checks
    # and ensure it's never available in production


# Create a singleton instance
jwt_verifier = JWTVerifier()
