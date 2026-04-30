from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ui_automation', '0004_wallet_launch_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='walletsession',
            name='process_id',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Chrome 进程 ID'),
        ),
    ]
