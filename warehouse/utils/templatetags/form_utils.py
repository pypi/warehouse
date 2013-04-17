from django import template


register = template.Library()


@register.simple_tag
def renderfield(field, **attrs):
    return field.as_widget(attrs=attrs)
