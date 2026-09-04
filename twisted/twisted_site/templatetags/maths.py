from django import template

register = template.Library()


@register.filter
def divide(x, y):
    return x / y
