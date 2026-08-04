from django.db.models.signals import post_save
from django.dispatch import receiver
from notifications.utils import send_policy_update_notification

from .models import (
    Privacy_Policy, Terms_Of_Service, Cookie_Policy,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy,
    Seller_Policy, Buyer_Protection_Policy, Prohibited_Products_Policy,
    Intellectual_Property_Policy, Community_Guidelines
)

POLICY_MODELS = (
    Privacy_Policy, Terms_Of_Service, Cookie_Policy,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy,
    Seller_Policy, Buyer_Protection_Policy, Prohibited_Products_Policy,
    Intellectual_Property_Policy, Community_Guidelines
)


@receiver(post_save, sender=Privacy_Policy)
@receiver(post_save, sender=Terms_Of_Service)
@receiver(post_save, sender=Cookie_Policy)
@receiver(post_save, sender=EMI_Payment_Policy)
@receiver(post_save, sender=Warranty_Policy)
@receiver(post_save, sender=Exchange_Policy)
@receiver(post_save, sender=Delivery_Policy)
@receiver(post_save, sender=PreOrder_Policy)
@receiver(post_save, sender=Refund_Policy)
@receiver(post_save, sender=Return_Policy)
@receiver(post_save, sender=Seller_Policy)
@receiver(post_save, sender=Buyer_Protection_Policy)
@receiver(post_save, sender=Prohibited_Products_Policy)
@receiver(post_save, sender=Intellectual_Property_Policy)
@receiver(post_save, sender=Community_Guidelines)
def handle_policy_update_notification(sender, instance, created, **kwargs):
    """
    Automatically notify all active users whenever a policy is updated or created.
    """
    policy_name = sender.__name__.replace("_", " ").strip()
    endpoint = sender._meta.model_name.replace("_", "-")
    cta_link = f"/api/policy/{endpoint}/"
    
    send_policy_update_notification(policy_name=policy_name, cta_link=cta_link)
