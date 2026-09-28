from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('eventhub', '0005_event_rubric')]

    operations = [
        migrations.AddConstraint(
            model_name='judge',
            constraint=models.UniqueConstraint(fields=('event', 'user'), name='unique_judge_event_user'),
        ),
    ]
