import json

from django.core import serializers
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.utils.encoding import force_unicode
from django.utils.text import capfirst
from django.utils.translation import ugettext as _

import papertrail
from papertrail.models import Entry


class AdminEventLoggerMixin(object):
    '''
    Mixin for ModelAdmin classes to log admin actions to the papertrail
    application as well as to Django's built-in admin logging.
    '''
    def _record_changes(self, obj, fields=None):
        '''
        Records the state of `obj` to a JSON-serializable object, optionally
        recording only values in a list of `fields`.  If `fields` is not
        specified, all fields will be recorded.
        '''
        rec = json.loads(serializers.serialize('json', [obj]))[0]
        if fields:
            rec['fields'] = {k: v for k, v in rec['fields'].items()
                             if k in fields}
        return rec

    def log_addition(self, request, object):
        super(AdminEventLoggerMixin, self).log_addition(request, object)

        fields = self._record_changes(object)['fields']
        return papertrail.log('admin-edit', 'Created object',
                data={'action': 'add', 'fields': fields},
                targets={
                   'acting_user': request.user,
                   'instance': object
               })

    def log_change(self, request, object, message):
        super(AdminEventLoggerMixin, self).log_change(request, object, message)

        # construct_change_message() creates a JSON message that we load and
        # store here. (In case we don't get JSON back for some reason, still
        # store the message)
        try:
            data = {'changes': json.loads(message)}
        except ValueError:
            data = {'message': message}
        return papertrail.log('admin-edit', 'Updated object',
                              data=data,
                              targets={
                                  'acting_user': request.user,
                                  'instance': object
                              })

    def log_deletion(self, request, object, object_repr):
        super(AdminEventLoggerMixin, self).log_deletion(request, object, object_repr)

        fields = self._record_changes(object)['fields']
        return papertrail.log('admin-edit', 'Deleted object',
                data={'action': 'add', 'fields': fields},
                targets={
                   'acting_user': request.user,
                   'instance': object
               })

    def construct_change_message(self, request, form, formsets):
        '''
        Construct a detailed change message from a changed object, including
        related objects updated via subforms.  Returns a JSON string containing
        a structure detailing the fields changed and their updated values.
        '''
        def add_related_change(changes, obj, action='change', fields=None):
            rec = self._record_changes(obj, fields=fields)
            rec['action'] = action
            changes['related_changes'].append(rec)
            return rec

        changes = {
            'action': 'change',
            'fields': self._record_changes(form.instance, form.changed_data)['fields'],
            'related_changes': [],
            }

        for formset in (formsets or []):
            for obj in formset.new_objects:
                add_related_change(changes, obj, action='add')
            for obj, changed_fields in formset.changed_objects:
                add_related_change(changes, obj, action='change', fields=changed_fields)
            for obj in formset.deleted_objects:
                add_related_change(changes, obj, action='add')

        return json.dumps(changes)


class AdminObjectPapertrailViewMixin(object):

    def get_urls(self):
        from django.conf.urls import patterns, url
        from functools import update_wrapper

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)
            return update_wrapper(wrapper, view)

        info = self.model._meta.app_label, self.model._meta.module_name

        urlpatterns = patterns('',
            url(r'^(.+)/papertrail/',
                wrap(self.view_papertrail_item),
                name=u'{0}_{1}_papertrail'.format(*info)),
        ) + super(AdminEventLoggerMixin, self).get_urls()

        return urlpatterns

    def view_papertrail_item(self, request, object_id, extra_context=None):
        get_object_or_404(self.model, id=object_id)
        view_papertrail = view_papertrail_action()
        return view_papertrail(self, request, self.model.objects.filter(id=object_id))


def view_papertrail_action(template=None, extra_context=None, use_related_field=None):
    '''
    Creates an admin action to render a papertrail view of a selected object or
    queryset.

    `template` can be used to override the default template resolution.

    `extra_context` will be provided to the template context while rendering

    `use_related_field` should be a double__underscore__delimited related field
    reference that specifies a related object for each object specified in the
    queryset.

    Usage:

    For simple uses, just call `view_papertrail_action` to generate a function
    to add to your admin object's actions list:

        actions = [
            view_papertrail_action(),
            ...
            ]

    If you want to dynamically update parameters based on the properties of
    the request or selected objects, create a custom action on the admin
    object:

        actions = [
            'my_custom_papertrail',
            ...
            ]

        def my_custom_papertrail(self, request, queryset):
            if queryset.count() % 2 == 0:
                template = 'admin/papertrail-even.html'
            else:
                template = 'admin/papertrail-odd.html'

            context = {'num_entries': queryset.count()}
            papertrail_action = view_papertrail_action(
                template=template,
                extra_context=extra_context,
                )
            return papertrail_action(self, request, queryset)
    '''
    def view_papertrail(self, request, queryset):
        template = template or self.papertrail_template
        use_related_field = use_related_field or self.papertrail_field

        # Map to alternate queryset if specified
        if use_related_field:
            queryset = _map_to_related_queryset(queryset, use_related_field)
        
        action_list = Entry.objects.related_to(queryset).select_related()
        opts = queryset.model._meta
        app_label = opts.app_label

        if queryset.count() == 1:
            obj = queryset[0]
            title = _('Paper Trail: %s') % force_unicode(obj)
        else:
            title = _('Paper Trail: %s %s') % (queryset.count(), opts.verbose_name_plural)

        context = {
            'title': title,
            'action_list': action_list,
            'module_name': capfirst(force_unicode(opts.verbose_name_plural)),
            'app_label': app_label,
            'opts': opts,
        }
        context.update(extra_context or {})

        return TemplateResponse(request, template or [
            "admin/%s/%s/object_papertrail.html" % (app_label, opts.object_name.lower()),
            "admin/%s/object_papertrail.html" % app_label,
            "admin/object_papertrail.html"
        ], context, current_app=self.admin_site.name)
    view_papertrail.short_description = 'View Paper Trail'

    return view_papertrail


def _map_to_related_queryset(queryset, field):
    '''
    Given a queryset and an double__underscore__delimited field relation,
    return a list of the objects that are the target of that relation for
    all objects in the queryset.
    '''
    model = queryset.model

    # The easy part is finding the pks of the related objects
    pks = queryset.values_list('{0}__pk'.format(field), flat=True)

    # The hard part is traversing the relation string and finding out what
    # model we're actually looking for.
    segments = field.split('__')
    for segment in segments:
        field = getattr(model, segment).field
        model = field.related.parent_model
    
    # Once we have both pieces, we can just query the model for the ids
    return model.objects.filter(pk__in=pks)

