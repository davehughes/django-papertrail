from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
import jsonfield


# Django 1.5 custom user compatibility
AUTH_USER_MODEL = 'auth.User'
try:
    from django.contrib.auth import get_user_model
    AUTH_USER_MODEL = get_user_model()
except ImportError as e:
    pass


class EntryManager(models.Manager):

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
        def coerce_to_queryset(instance_or_queryset):
            if isinstance(instance_or_queryset, models.Model):
                instance = instance_or_queryset
                return instance.__class__.objects.filter(pk=instance.pk)
            else:
                return instance_or_queryset

        entry_qs = self.get_query_set()
        all_relations = [(None, r) for r in relations] + named_relations.items()

        for name, relation in all_relations:
            related_qs = coerce_to_queryset(relation)
            content_type = ContentType.objects.get_for_model(related_qs.model)
            filters = {
                'related_objects__related_content_type': content_type,
                'related_objects__related_id__in': related_qs,
                }
            if name:
                filters.update({'related_objects__relation_name': name})

            entry_qs = entry_qs.filter(**filters)

        return entry_qs.distinct()


class Entry(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    label = models.CharField(max_length=255)
    type = models.CharField(max_length=50, null=True)
    data = jsonfield.JSONField(null=True)

    objects = EntryManager()

    class Meta:
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'


class EntryRelatedObject(models.Model):
    entry = models.ForeignKey('Entry', related_name='related_objects')
    relation_name = models.CharField(max_length=100)
    related_content_type = models.ForeignKey(ContentType)
    related_id = models.PositiveIntegerField()
    related_object = generic.GenericForeignKey('related_content_type', 'related_id')


@transaction.commit_on_success
def log(label, data=None, type=None, **related_objects):
    entry = Entry.objects.create(label=label, data=data, type=type)

    for name, instance in related_objects.items():
        EntryRelatedObject.objects.create(
            entry=entry,
            relation_name=name,
            related_object=instance
            )

    return entry
