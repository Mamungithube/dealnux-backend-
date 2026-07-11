import json
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from account.utils.auth import basic_auth_required


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


def health_check(request):
    """
    Lightweight, unauthenticated health check endpoint for uptime monitoring
    (e.g. UptimeRobot, load balancers, k8s liveness/readiness probes).
    Intentionally has NO basic_auth_required so monitoring tools can hit it freely.
    Keep this endpoint fast — avoid DB/external calls unless you need deep health checks.
    """
    return JsonResponse({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
    })