from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("celebrity", "0011_alter_actorimage_actor"),
    ]

    operations = [
        migrations.AddField(
            model_name="actorimage",
            name="face_encoding",
            field=models.JSONField(blank=True, editable=False, null=True),
        ),
    ]
