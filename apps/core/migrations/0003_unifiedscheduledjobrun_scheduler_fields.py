from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_unifiedscheduledjobrun_unifiedscheduledjobdependency'),
    ]

    operations = [
        migrations.AddField(
            model_name='unifiedscheduledjobrun',
            name='trigger_source',
            field=models.CharField(
                choices=[
                    ('manual', 'Manual'),
                    ('scheduler', 'Scheduler'),
                    ('retry', 'Retry'),
                ],
                default='manual',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='unifiedscheduledjobrun',
            name='scheduled_for',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='unifiedscheduledjobrun',
            name='locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='unifiedscheduledjobrun',
            name='worker_id',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='unifiedscheduledjobrun',
            name='retry_of',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='retry_runs',
                to='core.unifiedscheduledjobrun',
            ),
        ),
        migrations.AddIndex(
            model_name='unifiedscheduledjobrun',
            index=models.Index(fields=['trigger_source', '-created_at'], name='unified_sch_trigger_24d842_idx'),
        ),
        migrations.AddIndex(
            model_name='unifiedscheduledjobrun',
            index=models.Index(fields=['locked_until'], name='unified_sch_locked__ad53db_idx'),
        ),
        migrations.AddIndex(
            model_name='unifiedscheduledjobrun',
            index=models.Index(fields=['retry_of'], name='unified_sch_retry_o_eb1e99_idx'),
        ),
    ]
