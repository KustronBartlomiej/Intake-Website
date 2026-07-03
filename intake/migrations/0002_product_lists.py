import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_default_lists(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    ProductList = apps.get_model('intake', 'ProductList')
    QuickAddProduct = apps.get_model('intake', 'QuickAddProduct')

    user_ids = QuickAddProduct.objects.values_list('user_id', flat=True).distinct()
    for user_id in user_ids:
        user = User.objects.get(pk=user_id)
        default_list = ProductList.objects.create(owner=user, name='My products')
        QuickAddProduct.objects.filter(user_id=user_id).update(product_list=default_list)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('intake', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('is_public', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_lists', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='quickaddproduct',
            name='default_weight_g',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name='quickaddproduct',
            name='product_list',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='products', to='intake.productlist'),
        ),
        migrations.RunPython(create_default_lists, noop_reverse),
        migrations.AlterField(
            model_name='quickaddproduct',
            name='product_list',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='intake.productlist'),
        ),
        migrations.RemoveField(
            model_name='quickaddproduct',
            name='user',
        ),
        migrations.AlterModelOptions(
            name='quickaddproduct',
            options={'ordering': ['name']},
        ),
    ]
