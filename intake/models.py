from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    kcal_goal = models.PositiveIntegerField(default=2000)
    protein_goal = models.PositiveIntegerField(default=150)
    dark_mode = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.user.username} profile'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


class FoodEntry(models.Model):
    SOURCE_MANUAL = 'manual'
    SOURCE_QUICK = 'quick'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual'),
        (SOURCE_QUICK, 'Quick Add'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='entries')
    date = models.DateField()
    name = models.CharField(max_length=200)
    kcal_per_100g = models.DecimalField(max_digits=7, decimal_places=1)
    protein_per_100g = models.DecimalField(max_digits=6, decimal_places=1)
    weight_g = models.DecimalField(max_digits=7, decimal_places=1)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def total_kcal(self):
        return round(float(self.kcal_per_100g) * float(self.weight_g) / 100, 1)

    @property
    def total_protein(self):
        return round(float(self.protein_per_100g) * float(self.weight_g) / 100, 1)

    def __str__(self):
        return f'{self.name} ({self.date}) — {self.user.username}'


class ProductList(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_lists')
    name = models.CharField(max_length=100)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.owner.username})'


class QuickAddProduct(models.Model):
    product_list = models.ForeignKey(ProductList, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    kcal_per_100g = models.DecimalField(max_digits=7, decimal_places=1)
    protein_per_100g = models.DecimalField(max_digits=6, decimal_places=1)
    default_weight_g = models.DecimalField(max_digits=7, decimal_places=1, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} — {self.product_list.owner.username}'


class Friendship(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
    ]

    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friendships_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friendships_received')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['sender', 'recipient'], name='unique_friendship_direction'),
            models.CheckConstraint(
                condition=~models.Q(sender=models.F('recipient')),
                name='friendship_users_must_differ',
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.sender.username} → {self.recipient.username} ({self.status})'


class ProductEntryRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_DECLINED, 'Declined'),
    ]

    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_requests_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_requests_received')
    product = models.ForeignKey(
        QuickAddProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entry_requests',
    )
    product_name = models.CharField(max_length=200)
    kcal_per_100g = models.DecimalField(max_digits=7, decimal_places=1)
    protein_per_100g = models.DecimalField(max_digits=6, decimal_places=1)
    weight_g = models.DecimalField(max_digits=7, decimal_places=1)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    created_entry = models.OneToOneField(
        FoodEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_request',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.product_name}: {self.sender.username} → {self.recipient.username}'
