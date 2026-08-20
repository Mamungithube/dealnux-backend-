import json
import time
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from django.db import connection
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from account.utils.auth import basic_auth_required


# -------------------------- API Root Discovery & Info View --------------------------
@basic_auth_required
def api_root(request):
    """API root endpoint with project and documentation information"""
    base_url = request.build_absolute_uri('/')[:-1]

    response_data = {
        'welcome': {
            'message': 'Welcome to Dealnux API',
            'version': 'v1.0.0',
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
        },

        'documentation': {
            'swagger': {
                'url': f"{base_url}/api/docs/",
                'description': 'Interactive API documentation with Swagger UI',
            },
            'schema': {
                'url': f"{base_url}/api/schema/",
                'description': 'Raw OpenAPI 3.0 schema (JSON/YAML)',
            },
        },

        'api_info': {
            'base_url': base_url,
            'format': 'JSON',
            'authentication': 'Token-based (see documentation for details)',
            'rate_limiting': 'Enabled — see response headers for current limits',
        },

        'versioning': {
            'current_version': 'v1',
            'available_versions': ['v1'],
            'deprecation_policy': 'Deprecated versions will be announced at least 90 days in advance',
        },

        'status': {
            'health_check': f"{base_url}/health/",
        },

        'legal': {
            'terms_of_service': f"{base_url}/api/v1/policy/terms/",
            'privacy_policy': f"{base_url}/api/v1/policy/privacy/",
        },

        'support': {
            'contact': 'support@dealnux.com',
        },
    }

    # If client explicitly wants JSON (e.g. via Accept header or ?format=json), skip HTML wrapper
    wants_json = request.GET.get('format') == 'json' or 'application/json' in request.META.get('HTTP_ACCEPT', '')

    if wants_json:
        response = JsonResponse(response_data, json_dumps_params={'indent': 2, 'ensure_ascii': False})
    else:
        json_output = json.dumps(response_data, indent=2, ensure_ascii=False)

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dealnux API</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: 'Courier New', Courier, monospace;
            background: #f5f5f5;
            font-size: 14px;
            line-height: 1.6;
        }}
        pre {{
            margin: 20px;
            padding: 20px;
            background: white;
            border-radius: 5px;
            border: 1px solid #ddd;
            overflow-x: auto;
        }}
        .json-key {{ color: #0066cc; font-weight: bold; }}
        .json-string {{ color: #669900; }}
        .json-number {{ color: #ff6600; }}
        .json-boolean {{ color: #cc0000; }}
        .json-null {{ color: #cc0000; }}
        .json-url {{
            color: #0066cc;
            text-decoration: underline;
            cursor: pointer;
        }}
        .json-url:hover {{
            color: #0044aa;
        }}
    </style>
</head>
<body>
<pre id="json">{json_output}</pre>

<script>
function syntaxHighlight(json) {{
    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return json.replace(/("(\\u[a-zA-Z0-9]{{4}}|\\[^u]|[^\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g, function (match) {{
        var cls = 'json-number';
        if (/^"/.test(match)) {{
            if (/:$/.test(match)) {{
                cls = 'json-key';
            }} else {{
                cls = 'json-string';
                var urlMatch = match.match(/"(https?:\\/\\/[^"]+)"/);
                if (urlMatch) {{
                    var url = urlMatch[1];
                    return '"<a href="' + url + '" class="json-url" target="_blank">' + url + '</a>"';
                }}
            }}
        }} else if (/true|false/.test(match)) {{
            cls = 'json-boolean';
        }} else if (/null/.test(match)) {{
            cls = 'json-null';
        }}
        return '<span class="' + cls + '">' + match + '</span>';
    }});
}}

document.getElementById('json').innerHTML = syntaxHighlight(document.getElementById('json').textContent);
</script>
</body>
</html>"""

        response = HttpResponse(html_content, content_type='text/html; charset=utf-8')

    # Basic security headers
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'DENY'
    response['Cache-Control'] = 'no-store'
    return response


# -------------------------- System Health Check View (Ping / Deep Check) --------------------------
@extend_schema(
    summary="System Health Check",
    description="Provides lightweight or comprehensive health status for database, cache, celery, and system services.",
    parameters=[
        OpenApiParameter(
            name="full",
            type=OpenApiTypes.BOOL,
            location=OpenApiParameter.QUERY,
            description="If true, performs deep connectivity tests on DB, Cache, and background workers.",
            required=False,
            default=False
        )
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        503: OpenApiTypes.OBJECT
    },
    tags=["Health"]
)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Unauthenticated health check endpoint for uptime monitoring and readiness probes.
    Usage:
      - /health/ (Fast ping - for load balancers / liveness probes)
      - /health/?full=true (Deep check - verifies DB, Redis, Celery)
    """
    full_check = request.GET.get('full', '').lower() in ['true', '1', 'yes']

    if not full_check:
        return JsonResponse({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'services': {
                'api': 'ok'
            }
        }, status=status.HTTP_200_OK)

    # Deep Health Check
    services_status = {}
    is_healthy = True

    # 1. Database Check
    start_time = time.time()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
        db_latency = round((time.time() - start_time) * 1000, 2)
        services_status['database'] = {
            'status': 'healthy',
            'latency_ms': db_latency
        }
    except Exception as e:
        is_healthy = False
        services_status['database'] = {
            'status': 'unhealthy',
            'error': str(e)
        }

    # 2. Redis Cache Check
    start_time = time.time()
    try:
        cache_key = '_health_check_test_key'
        cache.set(cache_key, 'ok', timeout=10)
        cached_val = cache.get(cache_key)
        redis_latency = round((time.time() - start_time) * 1000, 2)
        if cached_val == 'ok':
            services_status['cache'] = {
                'status': 'healthy',
                'latency_ms': redis_latency
            }
        else:
            is_healthy = False
            services_status['cache'] = {
                'status': 'unhealthy',
                'error': 'Cache read/write verification failed'
            }
    except Exception as e:
        services_status['cache'] = {
            'status': 'unhealthy',
            'error': str(e)
        }

    # 3. Celery Worker Check
    try:
        from dealnux.celery import app as celery_app
        inspector = celery_app.control.inspect(timeout=0.5)
        active_workers = inspector.ping()
        if active_workers:
            services_status['celery'] = {
                'status': 'healthy',
                'workers_online': list(active_workers.keys())
            }
        else:
            services_status['celery'] = {
                'status': 'warning',
                'message': 'No active Celery workers responded to ping'
            }
    except Exception as e:
        services_status['celery'] = {
            'status': 'warning',
            'error': str(e)
        }

    response_data = {
        'status': 'healthy' if is_healthy else 'unhealthy',
        'timestamp': datetime.now().isoformat(),
        'services': services_status
    }

    http_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JsonResponse(response_data, status=http_code)