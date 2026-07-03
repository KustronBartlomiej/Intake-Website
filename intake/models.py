from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    kcal_goal = models.PositiveIntegerField(default=2000)
    protein_goal = models.PositiveIntegerField(default=150)

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
