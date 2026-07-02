from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def keys(dictionary):
    return [str(k) for k in dictionary.keys()]


@register.filter
def split(value, separator):
    return value.split(separator)
