from django.dispatch import receiver
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User, Group
from papertrail.models import Entry, log
from papertrail import signals


class TestBasic(TestCase):
    
    def test_entry_logging(self):

        log('test', 'Testing entry')

        user = User.objects.create_user('testuser', 'test@example.com')
        log('test-user-created', 'User created', targets={'user': user})

        group = Group.objects.create(name='Test Group')
        log('test-group-created', 'Group created', targets={'group': group})

        group.user_set.add(user)
        log('test-group-added-user', 'User added to group', targets={'user': user, 'group': group})

        log('test-extra-data', 'Testing extra data', data={'key': 'value'})

        tznow = timezone.now()
        overridden_timestamp_entry = log(
            'test-overridden-timestamp',
            'Testing overriding a timestamp for operations like importing',
            timestamp=tznow
            )
        self.assertEqual(tznow, overridden_timestamp_entry.timestamp)

        qs = Entry.objects.filter(type__startswith='test')
        self.assertEqual(qs.count(), 6)

        self.assertEqual(qs.related_to(user).count(), 2)
        self.assertEqual(qs.related_to(group).count(), 2)
        self.assertEqual(qs.related_to(user=user).count(), 2)
        self.assertEqual(qs.related_to(group=group).count(), 2)
        self.assertEqual(qs.related_to(user=group).count(), 0)
        self.assertEqual(qs.related_to(group=user).count(), 0)
        self.assertEqual(qs.related_to(user, group).count(), 1)
        self.assertEqual(qs.related_to(user=user, group=group).count(), 1)

        # test chaining and equivalence
        self.assertEqual(set(qs.related_to(user=user)
                               .related_to(group=group)
                               .values_list('id', flat=True)),
                         set(qs.related_to(user=user, group=group)
                               .values_list('id', flat=True)))

    def test_signals(self):

        event_logged_counter = [0]

        @receiver(signals.event_logged)
        def on_event_logged(sender, **kwargs):
            event_logged_counter[0] += 1
    
        log('test', 'Testing signal')
        self.assertEqual(event_logged_counter[0], 1)
