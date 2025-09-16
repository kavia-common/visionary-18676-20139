from flask_smorest import Blueprint
from flask.views import MethodView
import re
import requests
from webargs import fields

# Blueprint for Fetch endpoint with documentation metadata
blp = Blueprint(
    "Fetch",
    "fetch",
    url_prefix="/",
    description="Utility endpoint to fetch raw content from a web URL for testing/inspection purposes.",
)

# Simple HTTP/HTTPS URL regex for validation
_HTTP_URL_RE = re.compile(r"^(https?://)[^\s/$.?#].[^\s]*$", re.IGNORECASE)

def _is_valid_http_url(url: str) -> bool:
    """Validate that the provided URL uses HTTP or HTTPS and has a non-empty host/path."""
    if not isinstance(url, str):
        return False
    return bool(_HTTP_URL_RE.match(url.strip()))

# Request schema using webargs
fetch_args = {
    "url": fields.String(required=True, description="HTTP(S) URL to fetch content from."),
    "timeout": fields.Float(required=False, missing=10.0, description="Optional request timeout in seconds (default 10s, min 1s, max 30s)."),
    "as_text": fields.Boolean(required=False, missing=True, description="Return decoded text (true) or raw content base64 (false). Only text is supported currently."),
}


@blp.route("/fetch")
class FetchContent(MethodView):
    """
    Fetch content from a given HTTP(S) URL.

    PUBLIC_INTERFACE
    Summary:
        Fetch content from a web URL (HTTP/HTTPS) and return the raw text/HTML.
    Request Body (application/json):
        - url (string, required): The HTTP(S) URL to fetch from.
        - timeout (float, optional): Request timeout in seconds (default 10, min 1, max 30).
        - as_text (boolean, optional): If true, returns decoded text; currently only text is supported.
    Responses:
        200: { "status": "success", "message": "Content fetched", "content": "<html...>", "content_type": "text/html; charset=UTF-8", "url": "https://..." }
        400: { "status": "error", "message": "Invalid URL or payload", "details": "..."}
        408: { "status": "error", "message": "Request timed out", "details": "..."}
        422: { "status": "error", "message": "Unsupported content type for text return", "details": "..."}
        502: { "status": "error", "message": "Upstream fetch failed", "details": "..."}
        500: { "status": "error", "message": "Internal server error", "details": "..."}
    Notes:
        - Only HTTP and HTTPS schemes are allowed.
        - This is a utility/testing endpoint; no data is persisted.
    """
    @blp.arguments(fetch_args, location="json")
    @blp.response(200, example={"status": "success", "message": "Content fetched", "content": "<html>...</html>", "content_type": "text/html; charset=UTF-8", "url": "https://example.com"})
    @blp.doc(summary="Fetch raw web content by URL", description="Accepts a URL and returns the fetched content as plain text/HTML. Validates HTTP/HTTPS scheme and handles errors gracefully.", tags=["Fetch"])
    def post(self, args):
        url = args.get("url", "").strip()
        timeout_val = args.get("timeout", 10.0)
        as_text = args.get("as_text", True)

        # Validate URL
        if not _is_valid_http_url(url):
            return {"status": "error", "message": "Invalid URL. Only http/https URLs are allowed.", "details": "Provide a valid HTTP(S) URL in the 'url' field."}, 400

        # Constrain timeout
        try:
            timeout_val = float(timeout_val)
        except (ValueError, TypeError):
            timeout_val = 10.0
        timeout_val = min(max(timeout_val, 1.0), 30.0)

        # Perform fetch
        try:
            resp = requests.get(url, timeout=timeout_val, headers={"User-Agent": "Visionary-SearchService/1.0"})
        except requests.exceptions.Timeout as e:
            return {"status": "error", "message": "Request timed out", "details": str(e)}, 408
        except requests.exceptions.RequestException as e:
            # Network errors, connection, invalid URL, SSL errors etc.
            return {"status": "error", "message": "Upstream fetch failed", "details": str(e)}, 502
        except Exception as e:
            return {"status": "error", "message": "Internal server error", "details": str(e)}, 500

        content_type = resp.headers.get("Content-Type", "") or ""

        # Attempt to return text if requested
        if as_text:
            # Ensure content appears to be text-like
            if not content_type or ("text" in content_type.lower() or "json" in content_type.lower() or "xml" in content_type.lower() or "html" in content_type.lower()):
                # Decode using requests' apparent encoding fallback
                resp.encoding = resp.encoding or resp.apparent_encoding
                text_body = resp.text if resp.text is not None else ""
                return {
                    "status": "success",
                    "message": "Content fetched",
                    "content": text_body,
                    "content_type": content_type,
                    "url": url,
                    "http_status": resp.status_code,
                }, 200
            else:
                return {
                    "status": "error",
                    "message": "Unsupported content type for text return",
                    "details": f"Received content-type '{content_type}', which is not text-like.",
                    "url": url,
                }, 422

        # Future: if as_text is False, we could return base64 of resp.content. For now, enforce text path.
        return {
            "status": "error",
            "message": "Binary content return not supported yet",
            "details": "Set as_text=true to receive decoded textual content.",
            "url": url,
        }, 422
