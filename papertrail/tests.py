from django.test import TestCase
from django.contrib.auth.models import User, Group
from papertrail.models import Entry, log


class TestBasic(TestCase):
    
    def test_entry_logging(self):

        basic_entry = log('Testing entry')

        user = User.objects.create_user('testuser', 'test@example.com')
        user_entry = log('User created', user=user)

        group = Group.objects.create(name='Test Group')
        group_entry = log('Group created', group=group)

        group.user_set.add(user)
        user_group_entry = log('User added to group', user=user, group=group)

        extra_data_entry = log('Testing extra data', data={'key': 'value'})

        self.assertEqual(Entry.objects.count(), 5)

        self.assertEqual(Entry.objects.related_to(user).count(), 2)
        self.assertEqual(Entry.objects.related_to(group).count(), 2)
        self.assertEqual(Entry.objects.related_to(user=user).count(), 2)
        self.assertEqual(Entry.objects.related_to(group=group).count(), 2)
        self.assertEqual(Entry.objects.related_to(user=group).count(), 0)
        self.assertEqual(Entry.objects.related_to(group=user).count(), 0)
        self.assertEqual(Entry.objects.related_to(user, group).count(), 1)
        self.assertEqual(Entry.objects.related_to(user=user, group=group).count(), 1)
