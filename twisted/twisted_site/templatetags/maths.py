from django import template

register = template.Library()


@register.filter
def divide(x: float, y: float) -> float:
    return x / y
