import types
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.utils import timezone
from django.conf import settings
import jsonfield
from papertrail import signals

def coerce_to_queryset(instance_or_queryset):
    if isinstance(instance_or_queryset, models.Model):
        instance = instance_or_queryset
        return instance.__class__.objects.filter(pk=instance.pk)
    else:
        return instance_or_queryset


def related_to(obj, relation_name=None):
    '''
    Create a Q object expressing an event relation with an optional name.
    This is useful as a building block for Entry.objects.related_to(), and
    can be used to provide better query control for more complex queries
    without the boilerplate of directly querying an Entry's related objects.

    Example 1: OR query

        Entry.objects.filter(related_to(user1) | related_to(user2)).distinct()

    Example 2: building block to Entry.objects.related_to()
        
        The following are equivalent:

        Entry.objects.related_to(user=user1, group=group1)
        Entry.objects.filter(related_to(user1, 'user'))
                     .filter(related_to(group1, 'group'))

    '''
    related_qs = coerce_to_queryset(obj)
    content_type = ContentType.objects.get_for_model(related_qs.model)
    filters = {
        'targets__related_content_type': content_type,
        'targets__related_id__in': related_qs,
        }
    if relation_name:
        filters.update({'targets__relation_name': relation_name})
    return models.Q(**filters)


class EntryQuerySet(models.query.QuerySet):

    def related_to(self, *relations, **named_relations):
        '''
        Filter entries based on objects they pertain to, either generically or
        by a specific relation type.  If multiple relations are specified, the
        filter combines them with AND semantics.

        Examples:

            Tracking a simple 'follow' event where one user follows another,
            which is logged as:

            > user1 = User.objects.get(...)
            > user2 = User.objects.get(...)
            > log('User followed another user', follower=user1, following=user2)
            
            First, a simple query for all events for user1, regardless of
            the type of relationship:

            > Entry.objects.related_to(user1)
        
            Next, to query for events involving both user1 and user2.
            
            > Entry.objects.related_to(user1, user2)

            Finally, to query for specific relationships, such as user1
            following user2:

            > Entry.objects.related_to(follower=user1, following=user2)
        '''
        entry_qs = self
        all_relations = [(None, r) for r in relations] + named_relations.items()

        for name, relation in all_relations:
            entry_qs = entry_qs.filter(related_to(relation, name))

        return entry_qs.distinct('timestamp', 'id')


class EntryManager(models.Manager):

    def get_query_set(self):
        return EntryQuerySet(self.model)

    def __getattr__(self, attr, *args):
        # see https://code.djangoproject.com/ticket/15062 for details
        if attr.startswith("_"):
            raise AttributeError
        return getattr(self.get_query_set(), attr, *args)


class Entry(models.Model):
    timestamp = models.DateTimeField()
    type = models.CharField(max_length=50)
    message = models.CharField(max_length=255)
    data = jsonfield.JSONField(null=True)

    # Field for storing a custom 'key' for looking up specific events from
    # external sources.  This can be used to quickly and precisely look up
    # events that you can derive natural keys for, but aren't easily queryable
    # using Entry's other fields.
    external_key = models.CharField(max_length=255, null=True)

    objects = EntryManager()

    class Meta:
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'

    def get(self, target, default=None):
        try:
            return self[target]
        except KeyError:
            return default

    def set(self, target_name, val, replace=True):
        '''
        Sets the updated target value, optionally replacing the existing target
        by that name.  If `replace` is False, raises an error if the target
        already exists.  `val` is generally a Django model instance, but can
        also be a tuple of (content_type, id) to reference an object as the
        contenttypes app does (this also allows references to deleted objects).
        '''
        target = self.get(target_name)
        if target and not replace:
            raise ValueError('Target {} already exists for this event'.format(target_name))

        target = target or EntryRelatedObject(entry=self, relation_name=target_name)
        if type(val) == types.TupleType:
            content_type, object_id = val
            target.related_content_type = content_type
            target.related_id = object_id
            target.save()
        elif val:
            target.related_object = val
            target.save()
        return target

    @property
    def targets_map(self):
        return dict([(t.relation_name, t.related_object)
                     for t in self.targets.all()])

    def update(self, targets_map):
        for target, val in (targets_map or {}).items():
            self[target] = val

    def __getitem__(self, target_name):
        try:
            target = self.targets.get(relation_name=target_name)
            return target.related_object
        except EntryRelatedObject.DoesNotExist:
            raise KeyError
    
    def __setitem__(self, target, val):
        return self.set(target, val)

    def __contains__(self, target_name):
        return self.targets.filter(relation_name=target_name).count() != 0


class EntryRelatedObject(models.Model):
    entry = models.ForeignKey('Entry', related_name='targets')
    relation_name = models.CharField(max_length=100)
    related_content_type = models.ForeignKey(ContentType)
    related_id = models.PositiveIntegerField()
    related_object = generic.GenericForeignKey('related_content_type', 'related_id')


def replace_object_in_papertrail(old_obj, new_obj, entry_qs=None):
    entry_qs = entry_qs or Entry.objects.all()
    old_obj_type = ContentType.objects.get_for_model(old_obj.__class__)
    new_obj_type = ContentType.objects.get_for_model(new_obj.__class__)
    related_qs = (EntryRelatedObject.objects.filter(
        entry__in=entry_qs,
        related_content_type=old_obj_type,
        related_id=old_obj.pk
        ))
    related_qs.update(related_content_type=new_obj_type,
                      related_id=new_obj.pk)


def search(*args, **kwargs):
    '''
    search(User.objects.get(id=1))
    search(related_owner=User.objects.get(id=1))
    search(related_owner=User.objects.get(id=1),
           timestamp__range=(...),
           message__startswith='Hello World')
    '''
    related_args = args
    related_kwargs = {}
    filter_kwargs = {}
    for k, v in kwargs.items():
        if k.startswith('related_'):
            related_kwargs[k[8:]] = v
        else:
            filter_kwargs[k] = v

    qs = Entry.objects.related_to(*related_args, **related_kwargs)
    qs = qs.filter(**filter_kwargs)
    return qs


def log(event_type, message, data=None, timestamp=None, targets=None, external_key=None):
    try:
        timestamp = timestamp or timezone.now()
        with transaction.commit_on_success():

            # Enforce uniqueness on event_type/external_id if an external id is
            # provided
            if external_key:
                entry, created = Entry.objects.get_or_create(
                    type=event_type,
                    external_key=external_key,
                    defaults={
                        'message': message,
                        'data': data,
                        'timestamp': timestamp,
                        })
                if not created:
                    return
            else:
                entry = Entry.objects.create(
                        type=event_type,
                        message=message,
                        data=data,
                        timestamp=timestamp or timezone.now()
                        )

            entry.update(targets)
            if getattr(settings, 'PAPERTRAIL_SHOW', False):
                WARNING = u'\033[95m'
                ENDC = u'\033[0m'
                print WARNING + u'papertrail ' + ENDC + event_type + u" " + message
    except:
        raise
    else:
        signals.event_logged.send_robust(sender=entry)
        return entry
