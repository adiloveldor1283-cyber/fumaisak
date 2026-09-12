# main/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def dict_get(d, key):
    return d.get(key, {})

@register.filter
def intcomma(value):
    try:
        if value is None:
            return "0"
        val = int(float(value))
        return f"{val:,}".replace(",", " ")
    except (ValueError, TypeError):
        return value