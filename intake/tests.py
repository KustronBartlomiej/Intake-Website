from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import FoodEntry, Friendship, ProductEntryRequest, ProductList, QuickAddProduct


class IntakeFeatureTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='test-pass-123')
        self.bob = User.objects.create_user(username='bob', password='test-pass-123')
        self.charlie = User.objects.create_user(username='charlie', password='test-pass-123')
        self.product_list = ProductList.objects.create(owner=self.alice, name='Daily')
        self.apple = QuickAddProduct.objects.create(
            product_list=self.product_list,
            name='Apple',
            kcal_per_100g=Decimal('52.0'),
            protein_per_100g=Decimal('0.3'),
            default_weight_g=Decimal('150.0'),
        )
        QuickAddProduct.objects.create(
            product_list=self.product_list,
            name='Banana',
            kcal_per_100g=Decimal('89.0'),
            protein_per_100g=Decimal('1.1'),
        )

    def test_product_search_filters_by_name_and_renders_alphabet_index(self):
        self.client.force_login(self.alice)
        response = self.client.get(
            reverse('product_list_detail', args=[self.product_list.pk]),
            {'q': 'app'},
        )
        self.assertContains(response, 'Apple')
        self.assertNotContains(response, 'Banana')
        self.assertContains(response, 'id="letter-A"')
        self.assertContains(response, 'Search products by name')
        self.assertContains(response, 'Copy to another list')
        self.assertContains(response, 'Create another list before copying this product.')

    def test_friend_invitation_must_be_accepted(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse('friend_request_create'), {'username': 'bob'})
        self.assertRedirects(response, reverse('settings'))
        friendship = Friendship.objects.get(sender=self.alice, recipient=self.bob)
        self.assertEqual(friendship.status, Friendship.STATUS_PENDING)

        self.client.force_login(self.bob)
        self.client.post(reverse('friend_request_respond', args=[friendship.pk, 'accept']))
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, Friendship.STATUS_ACCEPTED)

    def test_cannot_create_duplicate_reverse_friendship(self):
        Friendship.objects.create(sender=self.alice, recipient=self.bob)
        self.client.force_login(self.bob)
        self.client.post(reverse('friend_request_create'), {'username': 'alice'})
        self.assertEqual(Friendship.objects.count(), 1)

    def test_only_friends_can_send_product_requests(self):
        self.client.force_login(self.alice)
        self.client.post(reverse('product_request_create', args=[self.apple.pk]), {
            'recipient': self.charlie.pk,
            'weight_g': '120',
            'date': str(date.today()),
        })
        self.assertFalse(ProductEntryRequest.objects.exists())

    def test_accepting_product_request_creates_exactly_one_entry_from_snapshot(self):
        Friendship.objects.create(
            sender=self.alice,
            recipient=self.bob,
            status=Friendship.STATUS_ACCEPTED,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse('product_request_create', args=[self.apple.pk]), {
            'recipient': self.bob.pk,
            'weight_g': '125',
            'date': str(date.today()),
        })
        product_request = ProductEntryRequest.objects.get()

        self.apple.name = 'Changed after sending'
        self.apple.kcal_per_100g = Decimal('999.0')
        self.apple.save()

        self.client.force_login(self.bob)
        accept_url = reverse('product_request_respond', args=[product_request.pk, 'accept'])
        self.client.post(accept_url)
        entry = FoodEntry.objects.get(user=self.bob)
        self.assertEqual(entry.name, 'Apple')
        self.assertEqual(entry.kcal_per_100g, Decimal('52.0'))
        self.assertEqual(entry.weight_g, Decimal('125.0'))

        second_response = self.client.post(accept_url)
        self.assertEqual(second_response.status_code, 404)
        self.assertEqual(FoodEntry.objects.filter(user=self.bob).count(), 1)

    def test_other_user_cannot_accept_product_request(self):
        product_request = ProductEntryRequest.objects.create(
            sender=self.alice,
            recipient=self.bob,
            product=self.apple,
            product_name='Apple',
            kcal_per_100g=Decimal('52.0'),
            protein_per_100g=Decimal('0.3'),
            weight_g=Decimal('100.0'),
            date=date.today(),
        )
        self.client.force_login(self.charlie)
        response = self.client.post(
            reverse('product_request_respond', args=[product_request.pk, 'accept'])
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(FoodEntry.objects.exists())

    def test_existing_daily_entry_can_be_sent_to_friend_as_snapshot(self):
        Friendship.objects.create(
            sender=self.alice,
            recipient=self.bob,
            status=Friendship.STATUS_ACCEPTED,
        )
        entry = FoodEntry.objects.create(
            user=self.alice,
            date=date.today(),
            name='Breakfast apple',
            kcal_per_100g=Decimal('52.0'),
            protein_per_100g=Decimal('0.3'),
            weight_g=Decimal('175.0'),
            source=FoodEntry.SOURCE_QUICK,
        )
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('entry_request_create', args=[entry.pk]),
            {'recipient': self.bob.pk, 'next': reverse('home')},
        )
        self.assertRedirects(response, reverse('home'))
        product_request = ProductEntryRequest.objects.get()
        self.assertIsNone(product_request.product)
        self.assertEqual(product_request.product_name, 'Breakfast apple')
        self.assertEqual(product_request.weight_g, Decimal('175.0'))

    def test_use_adds_to_owner_and_sends_friend_request_in_one_action(self):
        Friendship.objects.create(
            sender=self.alice,
            recipient=self.bob,
            status=Friendship.STATUS_ACCEPTED,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse('quick_add_use', args=[self.apple.pk]), {
            'weight_g': '140',
            'recipient': self.bob.pk,
        })
        entry = FoodEntry.objects.get(user=self.alice)
        product_request = ProductEntryRequest.objects.get(recipient=self.bob)
        self.assertEqual(entry.weight_g, Decimal('140.0'))
        self.assertEqual(product_request.weight_g, Decimal('140.0'))
        self.assertEqual(product_request.status, ProductEntryRequest.STATUS_PENDING)

    def test_ajax_use_returns_confirmation_without_redirect(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('quick_add_use', args=[self.apple.pk]),
            {'weight_g': '150'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'ok': True})
        self.assertTrue(FoodEntry.objects.filter(user=self.alice, name='Apple').exists())

    def test_product_copy_keeps_original_and_copies_all_values(self):
        target = ProductList.objects.create(owner=self.alice, name='Favourites')
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('product_copy', args=[self.apple.pk]),
            {'target_list': target.pk},
        )
        self.assertRedirects(response, reverse('product_list_detail', args=[self.product_list.pk]))
        self.assertTrue(QuickAddProduct.objects.filter(pk=self.apple.pk).exists())
        copied = target.products.get()
        self.assertNotEqual(copied.pk, self.apple.pk)
        self.assertEqual(copied.name, self.apple.name)
        self.assertEqual(copied.kcal_per_100g, self.apple.kcal_per_100g)
        self.assertEqual(copied.protein_per_100g, self.apple.protein_per_100g)
        self.assertEqual(copied.default_weight_g, self.apple.default_weight_g)

    def test_product_cannot_be_copied_to_another_users_list(self):
        target = ProductList.objects.create(owner=self.bob, name='Bob list')
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('product_copy', args=[self.apple.pk]),
            {'target_list': target.pk},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(target.products.exists())

    def test_cannot_send_another_users_daily_entry(self):
        Friendship.objects.create(
            sender=self.alice,
            recipient=self.bob,
            status=Friendship.STATUS_ACCEPTED,
        )
        entry = FoodEntry.objects.create(
            user=self.alice,
            date=date.today(),
            name='Private entry',
            kcal_per_100g=Decimal('10.0'),
            protein_per_100g=Decimal('1.0'),
            weight_g=Decimal('100.0'),
        )
        self.client.force_login(self.bob)
        response = self.client.post(
            reverse('entry_request_create', args=[entry.pk]),
            {'recipient': self.alice.pk},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProductEntryRequest.objects.exists())

    def test_recent_entry_can_be_added_again_with_identical_values(self):
        entry = FoodEntry.objects.create(
            user=self.alice,
            date=date.today(),
            name='Sausages',
            kcal_per_100g=Decimal('295.0'),
            protein_per_100g=Decimal('14.0'),
            weight_g=Decimal('22.0'),
            source=FoodEntry.SOURCE_QUICK,
        )
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('entry_repeat', args=[entry.pk]),
            {'next': reverse('home')},
        )
        self.assertRedirects(response, reverse('home'))
        repeated = FoodEntry.objects.filter(user=self.alice).exclude(pk=entry.pk).get()
        self.assertEqual(repeated.name, entry.name)
        self.assertEqual(repeated.date, entry.date)
        self.assertEqual(repeated.kcal_per_100g, entry.kcal_per_100g)
        self.assertEqual(repeated.protein_per_100g, entry.protein_per_100g)
        self.assertEqual(repeated.weight_g, entry.weight_g)

    def test_cannot_repeat_another_users_entry(self):
        entry = FoodEntry.objects.create(
            user=self.alice,
            date=date.today(),
            name='Private entry',
            kcal_per_100g=Decimal('10.0'),
            protein_per_100g=Decimal('1.0'),
            weight_g=Decimal('100.0'),
        )
        self.client.force_login(self.bob)
        response = self.client.post(reverse('entry_repeat', args=[entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(FoodEntry.objects.count(), 1)

    def test_notification_badge_counts_pending_items(self):
        Friendship.objects.create(sender=self.alice, recipient=self.bob)
        ProductEntryRequest.objects.create(
            sender=self.alice,
            recipient=self.bob,
            product=self.apple,
            product_name='Apple',
            kcal_per_100g=Decimal('52.0'),
            protein_per_100g=Decimal('0.3'),
            weight_g=Decimal('100.0'),
            date=date.today(),
        )
        self.client.force_login(self.bob)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.context['notification_count'], 2)
        self.assertContains(response, '2 unread')

    def test_dark_mode_setting_is_persisted_without_changing_goals(self):
        original_goals = (self.alice.profile.kcal_goal, self.alice.profile.protein_goal)
        self.client.force_login(self.alice)
        self.client.post(reverse('settings'), {'setting_type': 'appearance', 'dark_mode': 'on'})
        self.alice.profile.refresh_from_db()
        self.assertTrue(self.alice.profile.dark_mode)
        self.assertEqual(
            (self.alice.profile.kcal_goal, self.alice.profile.protein_goal),
            original_goals,
        )
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'class="h-full dark"')

    def test_settings_and_notifications_pages_render(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse('settings')).status_code, 200)
        self.assertEqual(self.client.get(reverse('notifications')).status_code, 200)
