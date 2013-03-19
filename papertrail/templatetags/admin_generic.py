from django import template
from django.db import models
from django.core.urlresolvers import reverse, NoReverseMatch

register = template.Library()

@register.filter
def adminview(value, view='change'):
    '''
    Given an instance (`value`), generate a link to the specified admin `view`.

    Example:
        {{ user|adminview:'history' }} -> /admin/user/{user_id}/history/
    '''
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

@register.filter
def has_papertrail(model_instance):
    url = adminview(model_instance, 'papertrail')
    return url is not None
