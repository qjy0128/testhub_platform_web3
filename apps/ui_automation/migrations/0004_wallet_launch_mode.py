from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ui_automation', '0003_walletsession_runtime_user_data_dir'),
    ]

    operations = [
        migrations.AddField(
            model_name='walletbrowserconfig',
            name='launch_mode',
            field=models.CharField(
                choices=[
                    ('runtime_clone', '克隆运行时 Profile'),
                    ('global_profile', '直连全局 Profile'),
                ],
                default='runtime_clone',
                max_length=50,
                verbose_name='启动模式',
            ),
        ),
        migrations.AddField(
            model_name='walletsession',
            name='launch_mode',
            field=models.CharField(
                choices=[
                    ('runtime_clone', '克隆运行时 Profile'),
                    ('global_profile', '直连全局 Profile'),
                ],
                default='runtime_clone',
                max_length=50,
                verbose_name='启动模式',
            ),
        ),
    ]
