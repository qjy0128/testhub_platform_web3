from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ui_automation', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WalletBrowserConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='配置名称')),
                ('wallet_provider', models.CharField(choices=[('metamask', 'MetaMask')], default='metamask', max_length=50, verbose_name='钱包提供方')),
                ('chrome_executable_path', models.CharField(max_length=500, verbose_name='Chrome 可执行路径')),
                ('user_data_dir', models.CharField(max_length=500, verbose_name='Chrome 用户数据目录')),
                ('profile_directory', models.CharField(default='Default', max_length=100, verbose_name='Chrome Profile 目录')),
                ('remote_debugging_port', models.PositiveIntegerField(default=9222, verbose_name='远程调试端口')),
                ('metamask_extension_id', models.CharField(blank=True, default='', max_length=64, verbose_name='MetaMask 扩展 ID')),
                ('force_close_existing_chrome', models.BooleanField(default=True, verbose_name='执行前关闭现有 Chrome')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='创建人')),
            ],
            options={
                'db_table': 'ui_wallet_browser_configs',
                'verbose_name': '钱包浏览器配置',
                'verbose_name_plural': '钱包浏览器配置',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='WalletSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wallet_provider', models.CharField(default='metamask', max_length=50, verbose_name='钱包提供方')),
                ('chrome_executable_path', models.CharField(max_length=500, verbose_name='Chrome 可执行路径')),
                ('user_data_dir', models.CharField(max_length=500, verbose_name='Chrome 用户数据目录')),
                ('profile_directory', models.CharField(default='Default', max_length=100, verbose_name='Chrome Profile 目录')),
                ('remote_debugging_port', models.PositiveIntegerField(default=9222, verbose_name='远程调试端口')),
                ('cdp_url', models.CharField(blank=True, default='', max_length=500, verbose_name='CDP URL')),
                ('debugger_address', models.CharField(blank=True, default='', max_length=100, verbose_name='调试地址')),
                ('metamask_extension_id', models.CharField(blank=True, default='', max_length=64, verbose_name='MetaMask 扩展 ID')),
                ('status', models.CharField(choices=[('pending', '待启动'), ('running', '运行中'), ('passed', '成功'), ('failed', '失败')], default='pending', max_length=20, verbose_name='状态')),
                ('error_message', models.TextField(blank=True, default='', verbose_name='错误信息')),
                ('started_at', models.DateTimeField(auto_now_add=True, verbose_name='开始时间')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='结束时间')),
                ('started_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='启动人')),
            ],
            options={
                'db_table': 'ui_wallet_sessions',
                'verbose_name': '钱包会话',
                'verbose_name_plural': '钱包会话',
                'ordering': ['-started_at'],
            },
        ),
        migrations.AddField(
            model_name='aiexecutionrecord',
            name='wallet_mode',
            field=models.BooleanField(default=False, verbose_name='是否启用钱包模式'),
        ),
        migrations.AddField(
            model_name='aiexecutionrecord',
            name='wallet_provider',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='钱包提供方'),
        ),
        migrations.AddField(
            model_name='aiexecutionrecord',
            name='wallet_target_chain',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='目标链'),
        ),
        migrations.AddField(
            model_name='aiexecutionrecord',
            name='wallet_session',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='execution_records', to='ui_automation.walletsession', verbose_name='钱包会话'),
        ),
        migrations.CreateModel(
            name='WalletActionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_name', models.CharField(choices=[('connect_wallet', '连接钱包'), ('switch_chain', '切链'), ('sign_message', '签名消息'), ('confirm_transaction', '确认交易')], max_length=50, verbose_name='动作名称')),
                ('action_status', models.CharField(choices=[('pending', '待执行'), ('passed', '成功'), ('failed', '失败')], default='pending', max_length=20, verbose_name='动作状态')),
                ('detail_message', models.TextField(blank=True, default='', verbose_name='详情')),
                ('payload', models.JSONField(default=dict, verbose_name='动作入参')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('execution_record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wallet_action_logs', to='ui_automation.aiexecutionrecord', verbose_name='AI 执行记录')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_logs', to='ui_automation.walletsession', verbose_name='钱包会话')),
            ],
            options={
                'db_table': 'ui_wallet_action_logs',
                'verbose_name': '钱包动作日志',
                'verbose_name_plural': '钱包动作日志',
                'ordering': ['created_at'],
            },
        ),
    ]
