from base64 import b32encode
from io import BytesIO

from api_alpha.utils.login_throttle import LoginRateThrottle
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.mfa import MFAError, confirm_enrollment, start_enrollment
from batid.services.user import login_response_body
from django_otp.qr import write_qrcode_image
from rest_framework import status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.response import Response

MFA_ERRORS = {
    MFAError.REQUIRED: (
        status.HTTP_401_UNAUTHORIZED,
        "Code d'authentification requis.",
    ),
    MFAError.INVALID: (
        status.HTTP_401_UNAUTHORIZED,
        "Code d'authentification invalide ou expiré. Patientez quelques secondes avant de réessayer.",
    ),
    MFAError.SETUP_REQUIRED: (
        status.HTTP_401_UNAUTHORIZED,
        "Configurez une application d'authentification pour vous connecter.",
    ),
    MFAError.ALREADY_CONFIGURED: (
        status.HTTP_409_CONFLICT,
        "Une application d'authentification est déjà configurée. Contactez le support pour la réinitialiser.",
    ),
    MFAError.SETUP_NOT_STARTED: (
        status.HTTP_400_BAD_REQUEST,
        "Commencez par configurer l'application d'authentification.",
    ),
}


def mfa_error_response(error: MFAError) -> Response:
    status_code, detail = MFA_ERRORS[error]
    return Response({"error": error.value, "detail": detail}, status=status_code)


def mfa_error_doc(*errors: MFAError) -> dict:
    """OpenAPI response listing the given MFA error codes."""
    return {
        "description": " ".join(
            f"`{error}` : {MFA_ERRORS[error][1]}" for error in errors
        ),
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "error": {
                            "type": "string",
                            "enum": [error.value for error in errors],
                        },
                        "detail": {"type": "string"},
                    },
                }
            }
        },
    }


CREDENTIALS_PROPERTIES = {
    "username": {
        "type": "string",
        "description": "Identifiant ou adresse e-mail du compte.",
        "example": "jdupont@exemple.fr",
    },
    "password": {"type": "string", "description": "Mot de passe du compte."},
}

LOGIN_BODY_PROPERTIES = {
    "id": {"type": "integer", "example": 12},
    "token": {
        "type": "string",
        "description": "Jeton d'API à envoyer dans l'en-tête `Authorization: Token <jeton>`.",
        "example": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
    },
    "username": {"type": "string", "example": "jdupont"},
    "groups": {
        "type": "array",
        "items": {"type": "string"},
        "example": ["Contributors"],
    },
}

BAD_CREDENTIALS_DOC = {"description": "Identifiant ou mot de passe incorrect."}


def credentials_body_doc(properties: dict) -> dict:
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": ["username", "password"],
                }
            }
        },
    }


class MFASetupView(ObtainAuthToken):
    throttle_classes = [LoginRateThrottle]
    throttle_scope = "login"

    @rnb_doc(
        {
            "post": {
                "summary": "Configuration de la double authentification",
                "description": "Génère une nouvelle application d'authentification (TOTP) non confirmée pour le compte, à confirmer avec `/auth/mfa/confirm/`. Refusé si une application est déjà confirmée.",
                "operationId": "setupMFA",
                "requestBody": credentials_body_doc(CREDENTIALS_PROPERTIES),
                "responses": {
                    "200": {
                        "description": "Données à saisir dans l'application d'authentification.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "otpauth_uri": {
                                            "type": "string",
                                            "example": "otpauth://totp/RNB%3Ajdupont?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&algorithm=SHA1&digits=6&period=30&issuer=RNB",
                                        },
                                        "secret": {
                                            "type": "string",
                                            "description": "Clé en base32, pour une saisie manuelle.",
                                            "example": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
                                        },
                                        "qr_code_svg": {
                                            "type": "string",
                                            "description": "QR code de `otpauth_uri`, au format SVG.",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "400": BAD_CREDENTIALS_DOC,
                    "409": mfa_error_doc(MFAError.ALREADY_CONFIGURED),
                },
            }
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        device = start_enrollment(user)
        if isinstance(device, MFAError):
            return mfa_error_response(device)

        qr_code = BytesIO()
        write_qrcode_image(device.config_url, qr_code)
        return Response(
            {
                "otpauth_uri": device.config_url,
                "secret": b32encode(device.bin_key).decode(),
                "qr_code_svg": qr_code.getvalue().decode(),
            }
        )


class MFAConfirmView(ObtainAuthToken):
    throttle_classes = [LoginRateThrottle]
    throttle_scope = "login"

    @rnb_doc(
        {
            "post": {
                "summary": "Confirmation de la double authentification",
                "description": "Confirme l'application d'authentification avec son premier code, connecte l'utilisateur et renvoie 10 codes de secours, affichés une seule fois.",
                "operationId": "confirmMFA",
                "requestBody": credentials_body_doc(
                    {
                        **CREDENTIALS_PROPERTIES,
                        "otp": {
                            "type": "string",
                            "description": "Code à 6 chiffres affiché par l'application.",
                            "example": "123456",
                        },
                    }
                ),
                "responses": {
                    "200": {
                        "description": "Application confirmée.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        **LOGIN_BODY_PROPERTIES,
                                        "backup_codes": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Codes de secours à usage unique.",
                                            "example": ["k3m7qz2a"],
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": f"Identifiant ou mot de passe incorrect, ou `{MFAError.SETUP_NOT_STARTED}` : {MFA_ERRORS[MFAError.SETUP_NOT_STARTED][1]}"
                    },
                    "401": mfa_error_doc(MFAError.INVALID),
                    "409": mfa_error_doc(MFAError.ALREADY_CONFIGURED),
                },
            }
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        codes = confirm_enrollment(user=user, otp=request.data.get("otp"))
        if isinstance(codes, MFAError):
            return mfa_error_response(codes)

        return Response({**login_response_body(user), "backup_codes": codes})
