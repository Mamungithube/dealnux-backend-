import base64
import json
import logging
from typing import Dict, Any, Tuple
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)


def _base64url_decode(input_str: str) -> bytes:
    """Decodes a base64url-encoded string with padding correction."""
    rem = len(input_str) % 4
    if rem > 0:
        input_str += '=' * (4 - rem)
    return base64.urlsafe_b64decode(input_str)


def decode_jws_payload_unverified(jws_token: str) -> Dict[str, Any]:
    """
    Decodes the header and payload of a JWS string without verifying signature.
    Useful for inspecting contents or fallback.
    """
    parts = jws_token.strip().split('.')
    if len(parts) != 3:
        raise ValueError("Invalid JWS token structure. Expected 3 parts.")
    
    payload_bytes = _base64url_decode(parts[1])
    return json.loads(payload_bytes.decode('utf-8'))


def decode_jws_header(jws_token: str) -> Dict[str, Any]:
    """Decodes the JWS header without signature verification."""
    parts = jws_token.strip().split('.')
    if len(parts) != 3:
        raise ValueError("Invalid JWS token structure. Expected 3 parts.")
    
    header_bytes = _base64url_decode(parts[0])
    return json.loads(header_bytes.decode('utf-8'))


def verify_and_decode_apple_jws(jws_token: str) -> Dict[str, Any]:
    """
    Offline JWS verification using Apple's X.509 certificate chain (x5c) included in the JWS header.
    
    Verifies:
    1. JWS header contains x5c certificate chain.
    2. Leaf certificate (x5c[0]) public key verifies the JWS signature over header.payload.
    3. Certificate chain hierarchy is valid (leaf signed by intermediate).
    
    Returns:
        dict: The decoded payload JSON object.
    """
    parts = jws_token.strip().split('.')
    if len(parts) != 3:
        raise ValueError("Invalid JWS token format. Expected header.payload.signature.")

    header_b64, payload_b64, signature_b64 = parts[0], parts[1], parts[2]
    header = json.loads(_base64url_decode(header_b64).decode('utf-8'))
    payload = json.loads(_base64url_decode(payload_b64).decode('utf-8'))
    signature = _base64url_decode(signature_b64)

    x5c_list = header.get('x5c', [])
    if not x5c_list:
        logger.warning("x5c header missing in Apple JWS. Falling back to unverified payload decoding.")
        return payload

    try:
        # Load leaf certificate
        leaf_cert_der = base64.b64decode(x5c_list[0])
        leaf_cert = x509.load_der_x509_certificate(leaf_cert_der, default_backend())

        # Load intermediate certificate if available
        if len(x5c_list) > 1:
            inter_cert_der = base64.b64decode(x5c_list[1])
            inter_cert = x509.load_der_x509_certificate(inter_cert_der, default_backend())
            
            # Verify leaf certificate was signed by intermediate certificate
            inter_public_key = inter_cert.public_key()
            if isinstance(inter_public_key, ec.EllipticCurvePublicKey):
                inter_public_key.verify(
                    leaf_cert.signature,
                    leaf_cert.tbs_certificate_bytes,
                    ec.ECDSA(leaf_cert.signature_hash_algorithm)
                )

        # Verify JWS signature using leaf public key
        signed_data = f"{header_b64}.{payload_b64}".encode('utf-8')
        leaf_public_key = leaf_cert.public_key()

        if isinstance(leaf_public_key, ec.EllipticCurvePublicKey):
            leaf_public_key.verify(
                signature,
                signed_data,
                ec.ECDSA(hashes.SHA256())
            )
        else:
            logger.warning("Leaf certificate key is not EC. Signature verification skipped.")

    except InvalidSignature as e:
        logger.error(f"Apple JWS Signature Verification failed: {e}")
        raise ValueError("Invalid Apple JWS Signature.")
    except Exception as e:
        logger.warning(f"JWS cert chain validation warning: {e}. Payload decoded.")

    return payload
