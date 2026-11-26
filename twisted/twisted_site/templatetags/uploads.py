import os

from django import template

register = template.Library()


@register.simple_tag
def r2_public_url() -> str:
    """Base URL that uploaded images are served from."""
    return os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
