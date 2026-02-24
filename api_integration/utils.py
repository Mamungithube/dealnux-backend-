import time
from rest_framework.views import exception_handler
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        # First error message বের করা
        errors = response.data
        first_message = "An error occurred"

        if isinstance(errors, dict):
            first_key = next(iter(errors))
            first_error = errors[first_key]
            if isinstance(first_error, list):
                first_message = str(first_error[0])
            else:
                first_message = str(first_error)
        elif isinstance(errors, list):
            first_message = str(errors[0])
        elif isinstance(errors, str):
            first_message = errors

        response.data = {
            "success": False,
            "code": response.status_code,
            "message": first_message,
            "timestamp": int(time.time()),
            "data": errors
        }

    return response