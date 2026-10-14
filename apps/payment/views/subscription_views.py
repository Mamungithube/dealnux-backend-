from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import stripe

from ..models import SubscriptionPlan, UserSubscription
from ..serializers import SubscriptionPlanSerializer
from ..utils import refresh_subscription_limits


class SubscriptionPlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(
            is_active=True).order_by('price')
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Subscription plans fetched.",
            "data": serializer.data
        })


class CreateSubscriptionCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        plan_id = request.data.get('plan_id')
        user = request.user

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"success": False, "message": "Invalid Plan selected."}, status=200)

        if plan.plan_type == 'FREE':
            if UserSubscription.objects.filter(user=user).exists():
                return Response({"success": False, "message": "You have already used your free trial or have an active plan."}, status=200)

            UserSubscription.objects.create(
                user=user,
                plan=plan,
                status='TRIAL',
                trial_ends_at=timezone.now() + timedelta(days=plan.trial_days),
                expires_at=timezone.now() + timedelta(days=plan.trial_days)
            )
            return Response({
                "success": True,
                "message": f"Free trial activated for {plan.trial_days} days."
            }, status=200)

        try:
            if plan.stripe_price_id and plan.stripe_price_id.strip():
                line_items = [{'price': plan.stripe_price_id.strip(), 'quantity': 1}]
            else:
                interval = 'year' if 'YEARLY' in plan.plan_type else 'month'
                line_items = [{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': plan.name},
                        'unit_amount': int(plan.price * 100),
                        'recurring': {'interval': interval}
                    },
                    'quantity': 1,
                }]

            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                payment_method_types=['card'],
                line_items=line_items,
                mode='subscription',
                return_url=settings.STRIPE_RETURN_URL +
                '?session_id={CHECKOUT_SESSION_ID}',
                metadata={
                    'user_id': user.id,
                    'plan_id': plan.id,
                    'type': 'subscription_payment'
                },
                customer_email=user.email,
            )

            sub = UserSubscription.objects.filter(user=user).first()
            stripe_cust_id = sub.stripe_customer_id if sub else None

            if not stripe_cust_id:
                try:
                    customer = stripe.Customer.create(
                        email=user.email,
                        metadata={'user_id': user.id}
                    )
                    stripe_cust_id = customer.id
                except Exception:
                    pass

            intent_params = {
                'amount': int(plan.price * 100),
                'currency': 'usd',
                'payment_method_types': ['card'],
                'metadata': {
                    'user_id': user.id,
                    'plan_id': plan.id,
                    'type': 'subscription_payment'
                }
            }
            if stripe_cust_id:
                intent_params['customer'] = stripe_cust_id

            mobile_intent = stripe.PaymentIntent.create(**intent_params)

            return Response({
                "success": True,
                "client_secret": session.client_secret,
                "payment_intent_client_secret": mobile_intent.client_secret,
                "plan_name": plan.name,
                "amount": float(plan.price)
            }, status=200)

        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=200)


class UserSubscriptionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sub = UserSubscription.objects.filter(user=request.user).first()
        if sub and sub.is_active:
            sub = refresh_subscription_limits(sub)
        has_used_trial = UserSubscription.objects.filter(
            user=request.user).exists()
        if not sub or not sub.is_active:
            return Response({
                "success": True,
                "data": {
                    "plan_name": "None",
                    "price": 0.0,
                    "status": "INACTIVE",
                    "is_active": False,
                    "has_used_trial": has_used_trial,
                    "access": "Local Products Only",
                    "features": []
                }
            })

        return Response({
            "success": True,
            "data": {
                "plan_name": sub.plan.name,
                "price": float(sub.plan.price),
                "renews_at": sub.expires_at,
                "status": sub.status,
                "is_active": sub.is_active,
                "has_used_trial": True,
                "days_remaining": sub.days_remaining,
                "clicks_left": sub.plan.clicks_per_day - sub.daily_click_count,
                "features": sub.plan.features
            }
        })


class ManageSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sub = UserSubscription.objects.filter(user=request.user).first()

        if not sub or not sub.stripe_customer_id:
            return Response({
                "success": False,
                "message": "No active paid subscription or billing record found."
            }, status=404)

        try:
            session = stripe.billing_portal.Session.create(
                customer=sub.stripe_customer_id,
                return_url=settings.STRIPE_RETURN_URL,
            )
            return Response({
                "success": True,
                "code": 200,
                "data": {"portal_url": session.url}
            })
        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)
