from django.dispatch import receiver
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType
from papertrail.models import Entry, related_to, log
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

        # test related_to Q object
        self.assertEqual(set(qs.related_to(user, group)
                               .values_list('id', flat=True)),
                         set(qs.filter(related_to(user))
                               .filter(related_to(group))
                               .values_list('id', flat=True)))

        self.assertEqual(qs.filter(related_to(user) | related_to(group))
                           .distinct().count(),
                         3)


    def test_signals(self):

        event_logged_counter = [0]

        @receiver(signals.event_logged)
        def on_event_logged(sender, **kwargs):
            event_logged_counter[0] += 1
    
        log('test', 'Testing signal')
        self.assertEqual(event_logged_counter[0], 1)

    def test_setters_and_getters(self):
        e = log('test-entry', 'Test Entry')
        self.assertEqual(e.targets_map, {})

        user = User.objects.create_user('testuser', 'test@example.com')
        e.set('target1', user)

        # Basic lookup
        self.assertEqual(e.get('target1'), user)
        self.assertEqual(e['target1'], user)

        # Invalid key lookup and getting a default for non-existent targets
        with self.assertRaises(KeyError):
            e['target2']
        self.assertEqual(e.get('target2'), None)
        self.assertEqual(e.get('target2', 'a-default-value'), 'a-default-value')

        # Contains ('in') implementation
        self.assertTrue('target1' in e)
        self.assertFalse('target2' in e)

        # Setting and retrieving a 'virtual' target
        user_type = ContentType.objects.get_for_model(User)
        e.set('virtual', (user_type, 10000))
        self.assertEqual(e['virtual'], None)
        self.assertEqual(e.get('virtual', 'a-default-value'), None)
        


