from django import template
from django.db import models
from django.core.urlresolvers import reverse, NoReverseMatch

register = template.Library()

@register.filter
def adminview(value, view='change'):
    if isinstance(value, models.Model):
        try:
            change_form_url = reverse(
                'admin:{app}_{module}_{view}'.format(
                    app=value._meta.app_label,
                    module=value._meta.module_name,
                    view=view
                    ),
                args=[value.pk]
            )
            return change_form_url
        except NoReverseMatch:
            pass
    return None
