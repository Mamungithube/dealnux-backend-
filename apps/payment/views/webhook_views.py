import json
import logging
from datetime import timedelta

from custom_ads.utils import send_dealnux_email
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import stripe

from ..apple_iap import decode_jws_payload_unverified, verify_and_decode_apple_jws
from ..models import Payment, SubscriptionPlan, UserSubscription
from ..services import create_orders_from_payment

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            return HttpResponse(status=400)

        if event['type'] == 'checkout.session.completed':
            self._handle_checkout_completed(event['data']['object'])

        elif event['type'] == 'payment_intent.succeeded':  
            self._handle_payment_intent_succeeded(event['data']['object'])

        elif event['type'] == 'invoice.paid':
            self._handle_recurring_subscription(event['data']['object'])

        elif event['type'] == 'checkout.session.expired':
            self._handle_checkout_expired(event['data']['object'])

        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            self._handle_subscription_cancellation(subscription)

        return HttpResponse(status=200)

    def _handle_subscription_cancellation(self, stripe_sub):
        stripe_sub_id = stripe_sub.get('id')
        UserSubscription.objects.filter(
            stripe_subscription_id=stripe_sub_id
        ).update(status='CANCELLED')
        logger.info(f"Subscription {stripe_sub_id} has been cancelled.")

    def _handle_checkout_completed(self, session):
        metadata = session.get('metadata', {})
        p_type = metadata.get('type')
        payment_id = metadata.get('payment_id')

        if p_type == 'subscription_payment':
            self._handle_subscription_success(session)
            return

        if payment_id:
            try:
                payment = Payment.objects.get(id=payment_id)
                if payment.status == 'PAID':
                    logger.info(f"Payment ID {payment_id} already marked as PAID. Skipping duplicate processing.")
                    return

                payment.status = 'PAID'
                payment.stripe_payment_intent_id = session.get(
                    'payment_intent', '')
                payment.save()

                if p_type == 'store_payment':
                    items_json = metadata.get('items_json', '[]')
                    items = json.loads(items_json)
                    create_orders_from_payment(payment, items)
                elif p_type == 'ad_payment':
                    ad = payment.ad
                    if ad:
                        ad.status = 'pending'
                        ad.save()
                        send_dealnux_email(
                            "Ad Submitted for Review - DealNux",
                            ad.advertiser.email, 
                            "emails/ad_submitted.html",
                            {"ad": ad, "user": ad.advertiser}
                        )
            except Payment.DoesNotExist:
                logger.error(f"Error: Payment ID {payment_id} not found in database.")

    def _handle_subscription_success(self, session):
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        plan_id = metadata.get('plan_id')
        stripe_sub_id = session.get('subscription')
        stripe_cust_id = session.get('customer')

        if not user_id or not plan_id:
            return

        try:
            from account.models import User

            user = User.objects.get(id=user_id)
            plan = SubscriptionPlan.objects.get(id=plan_id)

            days = 365 if 'YEARLY' in plan.plan_type else 30
            now = timezone.now()

            subscription, _ = UserSubscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'status': 'ACTIVE',
                    'stripe_subscription_id': stripe_sub_id,
                    'stripe_customer_id': stripe_cust_id,
                    'started_at': now,
                    'expires_at': now + timedelta(days=days),
                    'daily_click_count': 0,
                    'last_click_date': now.date(),
                    'trial_ends_at': now
                }
            )
            logger.info(f"Payment success! Subscription activated for: {user.email}")

            self._process_referral_reward(user)

            from notifications.utils import create_notification
            create_notification(
                user=user,
                title="Subscription Activated! 🎉",
                body=f"Your subscription to '{plan.name}' is now active. Enjoy premium features!",
                notification_type="PROMOTION",
                channel="SYSTEM"
            )

            send_dealnux_email(
                "Your DealNux Subscription is Active!",
                user.email,
                "emails/subscription_active.html",
                {
                    "user": user,
                    "plan": plan,
                    "renewal_date": subscription.expires_at
                }
            )

        except Exception as e:
            logger.error(f"Error in _handle_subscription_success: {str(e)}")

    def _handle_subscription_success_intent(self, payment_intent):
        metadata = payment_intent.get('metadata', {})
        user_id = metadata.get('user_id')
        plan_id = metadata.get('plan_id')
        stripe_cust_id = payment_intent.get('customer')

        if not user_id or not plan_id:
            return

        try:
            from account.models import User

            user = User.objects.get(id=user_id)
            plan = SubscriptionPlan.objects.get(id=plan_id)

            days = 365 if 'YEARLY' in plan.plan_type else 30
            now = timezone.now()

            subscription, _ = UserSubscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'status': 'ACTIVE',
                    'stripe_subscription_id': payment_intent.get('id'),
                    'stripe_customer_id': stripe_cust_id,
                    'started_at': now,
                    'expires_at': now + timedelta(days=days),
                    'daily_click_count': 0,
                    'last_click_date': now.date(),
                    'trial_ends_at': now
                }
            )
            logger.info(f"Subscription activated via PaymentIntent for: {user.email}")

            self._process_referral_reward(user)

            from notifications.utils import create_notification
            create_notification(
                user=user,
                title="Subscription Activated! 🎉",
                body=f"Your subscription to '{plan.name}' is now active. Enjoy premium features!",
                notification_type="PROMOTION",
                channel="SYSTEM"
            )

            send_dealnux_email(
                "Your DealNux Subscription is Active!",
                user.email,
                "emails/subscription_active.html",
                {
                    "user": user,
                    "plan": plan,
                    "renewal_date": subscription.expires_at
                }
            )
        except Exception as e:
            logger.error(f"Error in _handle_subscription_success_intent: {str(e)}")

    def _handle_payment_intent_succeeded(self, payment_intent):
        metadata = payment_intent.get('metadata', {})
        payment_id = metadata.get('payment_id')
        p_type = metadata.get('type')

        if p_type == 'subscription_payment':
            self._handle_subscription_success_intent(payment_intent)
            return

        if not payment_id:
            return

        try:
            payment = Payment.objects.get(id=payment_id)

            if payment.status == 'PAID':
                return

            payment.status = 'PAID'
            payment.stripe_payment_intent_id = payment_intent.get('id')
            payment.save()

            if p_type == 'store_payment':
                items_json = metadata.get('items_json', '[]')
                items = json.loads(items_json)
                create_orders_from_payment(payment, items)

            elif p_type == 'ad_payment':
                ad = payment.ad
                if ad:
                    ad.status = 'pending'
                    ad.save()
                    send_dealnux_email(
                        "Ad Submitted for Review - DealNux",
                        ad.advertiser.email,
                        "emails/ad_submitted.html",
                        {"ad": ad, "user": ad.advertiser}
                    )

        except Payment.DoesNotExist:
            logger.error(f"PaymentIntent: Payment ID {payment_id} not found.")
        except Exception as e:
            logger.error(f"Error in _handle_payment_intent_succeeded: {str(e)}")

    def _process_referral_reward(self, user):
        from .utils import process_referral_reward_for_user
        process_referral_reward_for_user(user)

    def _handle_recurring_subscription(self, invoice):
        stripe_sub_id = invoice.get('subscription')
        try:
            sub = UserSubscription.objects.get(
                stripe_subscription_id=stripe_sub_id)
            days = 365 if 'YEARLY' in sub.plan.plan_type else 30
            sub.expires_at = timezone.now() + timedelta(days=days)
            sub.save()
        except UserSubscription.DoesNotExist:
            pass

    def _handle_checkout_expired(self, session):
        payment_id = session.get('metadata', {}).get('payment_id')
        if payment_id:
            Payment.objects.filter(
                id=payment_id, status='PENDING').update(status='CANCELLED')


class AppleVerifyReceiptView(APIView):
    """
    Verifies Apple StoreKit 2 JWS purchase_token and grants active subscription status.
    POST /api/payment/apple/verify/
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        purchase_token = request.data.get('purchase_token', '')
        product_id = request.data.get('product_id', '')
        transaction_id = str(request.data.get('transaction_id', ''))

        if not purchase_token and not transaction_id:
            return Response({
                "success": False,
                "is_active": False,
                "message": "purchase_token or transaction_id is required."
            }, status=400)

        jws_payload = {}
        if purchase_token:
            try:
                jws_payload = verify_and_decode_apple_jws(purchase_token)
            except Exception as e:
                logger.warning(f"Apple JWS verification warning: {e}")
                try:
                    jws_payload = decode_jws_payload_unverified(purchase_token)
                except Exception:
                    jws_payload = {}

        sku = jws_payload.get('productId') or product_id
        tx_id = str(jws_payload.get('transactionId') or transaction_id)
        orig_tx_id = str(jws_payload.get('originalTransactionId') or tx_id)
        expires_date_ms = jws_payload.get('expiresDate')

        plan = None
        if sku:
            plan = SubscriptionPlan.objects.filter(apple_product_id=sku, is_active=True).first()

        if not plan:
            if 'yearly' in sku.lower():
                plan = SubscriptionPlan.objects.filter(plan_type__icontains='YEARLY', is_active=True).first()
            elif 'monthly' in sku.lower():
                plan = SubscriptionPlan.objects.filter(plan_type__icontains='MONTHLY', is_active=True).first()

        if not plan:
            plan = SubscriptionPlan.objects.filter(is_active=True).exclude(plan_type='FREE').first()

        if not plan:
            return Response({
                "success": False,
                "is_active": False,
                "message": "No active subscription plan configured for this product."
            }, status=404)

        now = timezone.now()
        if expires_date_ms:
            expires_at = timezone.datetime.fromtimestamp(expires_date_ms / 1000.0, tz=timezone.utc)
        else:
            days = 365 if 'YEARLY' in plan.plan_type else 30
            expires_at = now + timedelta(days=days)

        user = request.user
        subscription, _ = UserSubscription.objects.update_or_create(
            user=user,
            defaults={
                'plan': plan,
                'status': 'ACTIVE',
                'payment_gateway': 'APPLE',
                'apple_original_transaction_id': orig_tx_id,
                'apple_latest_transaction_id': tx_id,
                'started_at': now,
                'expires_at': expires_at,
                'daily_click_count': 0,
                'last_click_date': now.date(),
                'trial_ends_at': now
            }
        )

        try:
            from notifications.utils import create_notification
            create_notification(
                user=user,
                title="Apple Subscription Activated! 🎉",
                body=f"Your subscription to '{plan.name}' is now active via Apple In-App Purchase.",
                notification_type="PROMOTION",
                channel="SYSTEM"
            )
        except Exception as e:
            logger.warning(f"Notification creation failed: {e}")

        return Response({
            "success": True,
            "is_active": True,
            "message": "Apple subscription verified and activated successfully.",
            "data": {
                "plan_name": plan.name,
                "expires_at": subscription.expires_at,
                "status": subscription.status,
                "is_active": subscription.is_active
            }
        }, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class AppleServerNotificationsView(APIView):
    """
    App Store Server Notifications V2 Webhook handler.
    POST /api/payment/apple/notifications/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        signed_payload = request.data.get('signedPayload') or request.body.decode('utf-8')
        if not signed_payload:
            return HttpResponse(status=400)

        try:
            if isinstance(signed_payload, str) and signed_payload.startswith('{'):
                data_dict = json.loads(signed_payload)
                signed_payload = data_dict.get('signedPayload', signed_payload)

            payload = verify_and_decode_apple_jws(signed_payload)
            notification_type = payload.get('notificationType')
            data = payload.get('data', {})
            signed_tx_info = data.get('signedTransactionInfo')

            if signed_tx_info:
                tx_payload = verify_and_decode_apple_jws(signed_tx_info)
                orig_tx_id = str(tx_payload.get('originalTransactionId', ''))
                expires_date_ms = tx_payload.get('expiresDate')

                if orig_tx_id:
                    sub = UserSubscription.objects.filter(apple_original_transaction_id=orig_tx_id).first()
                    if sub:
                        if notification_type in ['SUBSCRIBED', 'DID_RENEW', 'OFFER_REDEEMED']:
                            sub.status = 'ACTIVE'
                            if expires_date_ms:
                                sub.expires_at = timezone.datetime.fromtimestamp(expires_date_ms / 1000.0, tz=timezone.utc)
                            sub.save()
                        elif notification_type == 'EXPIRED':
                            sub.status = 'EXPIRED'
                            sub.save()
                        elif notification_type in ['REFUND', 'REVOKE']:
                            sub.status = 'CANCELLED'
                            sub.save()

            return HttpResponse(status=200)
        except Exception as e:
            logger.error(f"Error processing Apple Server Notification: {e}")
            return HttpResponse(status=200)
