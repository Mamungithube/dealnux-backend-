import time
from rest_framework.response import Response


def success_response(data=None, message="Success", code=200):
    """
    Standard successful JSON API response structure for DealNux.
    Preserves existing data and pagination payload format.
    """
    response = {
        "success": True,
        "code": code,
        "message": message,
        "timestamp": int(time.time()),
        "data": data if data is not None else {},
    }
    if isinstance(data, dict) and 'pagination' in data:
        response['pagination'] = data.pop('pagination')
    return Response(response, status=code)


def error_response(message="Error", code=400, data=None):
    """
    Standard error JSON API response structure for DealNux.
    """
    response = {
        "success": False,
        "code": code,
        "message": message,
        "timestamp": int(time.time()),
        "data": data or {},
    }
    return Response(response, status=code)
