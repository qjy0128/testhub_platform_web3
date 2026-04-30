from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ui_automation', '0002_wallet_automation'),
    ]

    operations = [
        migrations.AddField(
            model_name='walletsession',
            name='runtime_user_data_dir',
            field=models.CharField(blank=True, default='', max_length=500, verbose_name='Wallet runtime user data dir'),
        ),
    ]
