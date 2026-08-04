from django.db.models.signals import post_save
from django.dispatch import receiver
from notifications.utils import send_policy_update_notification

from .models import (
    Privacy_Policy, Terms_Of_Service, Cookie_Policy,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy,
    Seller_Policy, Buyer_Protection_Policy, Prohibited_Products_Policy,
    Intellectual_Property_Policy, Community_Guidelines, About_Us
)

POLICY_META = {
    Privacy_Policy: ("Privacy Policy", "/privacy-policy/"),
    Terms_Of_Service: ("Terms of Service", "/terms-of-service/"),
    Cookie_Policy: ("Cookie Policy", "/cookie-policy/"),
    EMI_Payment_Policy: ("EMI & Payment Policy", "/emi-payment-policy/"),
    Warranty_Policy: ("Warranty Policy", "/warranty-policy/"),
    Exchange_Policy: ("Exchange Policy", "/exchange-policy/"),
    Delivery_Policy: ("Delivery Policy", "/delivery-policy/"),
    PreOrder_Policy: ("Pre-Order Policy", "/pre-order-policy/"),
    Refund_Policy: ("Refund Policy", "/refund-policy/"),
    Return_Policy: ("Return Policy", "/return-policy/"),
    Seller_Policy: ("Seller Policy", "/seller-policy/"),
    Buyer_Protection_Policy: ("Buyer Protection Policy", "/buyer-protection-policy/"),
    Prohibited_Products_Policy: ("Prohibited Products Policy", "/prohibited-products-policy/"),
    Intellectual_Property_Policy: ("Intellectual Property Policy", "/intellectual-property-policy/"),
    Community_Guidelines: ("Community Guidelines", "/community-guidelines/"),
    About_Us: ("About Us", "/about-us/"),
}


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
@receiver(post_save, sender=About_Us)
def handle_policy_update_notification(sender, instance, created, **kwargs):
    """
    Automatically notify all active users whenever a policy or About Us page is updated or created.
    """
    meta = POLICY_META.get(sender)
    if meta:
        policy_name, cta_link = meta
    else:
        policy_name = sender.__name__.replace("_", " ").strip()
        cta_link = f"/{sender._meta.model_name.replace('_', '-')}/"

    send_policy_update_notification(policy_name=policy_name, cta_link=cta_link)
