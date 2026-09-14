"""
Artifact Generation Tool.
"""
import re
import logging
from typing import Dict, Any

logger = logging.getLogger("lenny_growth.tools.artifact_gen")

ARTIFACT_TOOL_SCHEMA = {
    "name": "artifact_gen",
    "description": "Generates a structured, shareable document artifact (Markdown strategy doc, framework cheat-sheet, or styled HTML executive memo) from transcript insights.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Descriptive title for the artifact."
            },
            "artifact_type": {
                "type": "string",
                "enum": ["essay", "markdown", "html"],
                "description": "Type of artifact to produce: 'essay' (Ship30), 'markdown' (standard doc), or 'html' (styled document)."
            },
            "content": {
                "type": "string",
                "description": "The complete markdown or HTML content of the artifact."
            }
        },
        "required": ["title", "artifact_type", "content"]
    }
}


def sanitize_html_content(raw_html: str) -> str:
    cleaned = raw_html
    cleaned = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'href=[\'"]javascript:[^\'"]*[\'"]', 'href="#"', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\son\w+=["\'][^"\']*["\']', '', cleaned, flags=re.IGNORECASE)
    return cleaned


def execute_artifact_gen(title: str, artifact_type: str, content: str) -> Dict[str, Any]:
    clean_content = content
    if artifact_type == "html":
        clean_content = sanitize_html_content(content)
        if not ("<!DOCTYPE" in clean_content.upper() or "<HTML" in clean_content.upper()):
            clean_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      color: #1e293b;
      background: #ffffff;
      padding: 24px;
      max-width: 720px;
      margin: 0 auto;
    }}
    h1 {{ color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
    h2, h3 {{ color: #1e293b; margin-top: 20px; }}
    .badge {{ background: #eff6ff; color: #1d4ed8; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; display: inline-block; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; }}
    ul, ol {{ padding-left: 20px; }}
    li {{ margin-bottom: 8px; }}
    strong {{ color: #0f172a; }}
    blockquote {{ border-left: 4px solid #3b82f6; margin: 0; padding-left: 16px; color: #475569; font-style: italic; }}
  </style>
</head>
<body>
  <div class="badge">Lenny Growth Artifact</div>
  <h1>{title}</h1>
  {clean_content}
</body>
</html>"""

    return {
        "title": title,
        "artifact_type": artifact_type,
        "content": clean_content
    }
