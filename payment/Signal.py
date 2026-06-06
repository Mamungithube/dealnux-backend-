# logic to run during user registration or first login
from .models import SubscriptionPlan, UserSubscription
from django.utils import timezone
from datetime import timedelta



def assign_free_trial(user):
    free_plan = SubscriptionPlan.objects.get(plan_type='FREE')
    duration = free_plan.trial_days 
    
    UserSubscription.objects.create(
        user=user,
        plan=free_plan,
        expires_at=timezone.now() + timedelta(days=duration)
    )