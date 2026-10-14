from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0013_profile_address_2_profile_city_profile_country_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='has_referral_reward_awarded',
            field=models.BooleanField(default=False),
        ),
    ]
