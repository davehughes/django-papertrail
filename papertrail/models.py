import types
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.utils import timezone
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

    objects = EntryManager()

    class Meta:
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'


class EntryRelatedObject(models.Model):
    entry = models.ForeignKey('Entry', related_name='targets')
    relation_name = models.CharField(max_length=100)
    related_content_type = models.ForeignKey(ContentType)
    related_id = models.PositiveIntegerField()
    related_object = generic.GenericForeignKey('related_content_type', 'related_id')


def log(event_type, message, data=None, timestamp=None, targets=None):

    try:
        with transaction.commit_on_success():
            entry = Entry.objects.create(
                    type=event_type,
                    message=message,
                    data=data,
                    timestamp=timestamp or timezone.now()
                    )

            for name, instance in (targets or {}).items():
                
                # Allow legacy/imported objects to be logged with a tuple specifying
                # (content_type, object_id)
                if type(instance) is tuple:
                    content_type, object_id = instance
                    EntryRelatedObject.objects.create(
                        entry=entry,
                        relation_name=name,
                        related_content_type=content_type,
                        related_id=object_id,
                        )
                
                # Create related object in the standard way
                elif instance:
                    EntryRelatedObject.objects.create(
                        entry=entry,
                        relation_name=name,
                        related_object=instance,
                        )
    except:
        raise
    else:
        signals.event_logged.send_robust(sender=entry)
        return entry
