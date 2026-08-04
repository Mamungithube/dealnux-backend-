from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import (
    Privacy_Policy, Terms_Of_Service, Cookie_Policy, Review,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy, About_Us,
    Seller_Policy, Buyer_Protection_Policy, Prohibited_Products_Policy,
    Intellectual_Property_Policy, Community_Guidelines
)


from django.forms import Textarea
from django.utils.safestring import mark_safe
from django.db import models


class RichTextEditorWidget(Textarea):
    """
    Visual WYSIWYG Rich Text Editor Widget (TinyMCE CDN)
    Allows non-technical admins to format text visually (Bold, Italic, Headings, Lists, Links)
    without writing any HTML tags manually.
    """
    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        element_id = attrs.get('id', f'id_{name}')
        init_js = f"""
        <script src="https://cdnjs.cloudflare.com/ajax/libs/tinymce/6.8.2/tinymce.min.js" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
        <script>
            (function() {{
                function initEditor() {{
                    if (window.tinymce) {{
                        tinymce.remove('#{element_id}');
                        tinymce.init({{
                            selector: '#{element_id}',
                            height: 520,
                            branding: false,
                            promotion: false,
                            menubar: 'edit insert format table',
                            plugins: 'advlist autolink lists link image charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime table help wordcount',
                            toolbar: 'undo redo | blocks | bold italic underline | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | link table | removeformat code fullscreen',
                            content_style: 'body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 15px; line-height: 1.6; padding: 12px; }}'
                        }});
                    }}
                }}
                if (document.readyState === 'complete' || document.readyState === 'interactive') {{
                    setTimeout(initEditor, 300);
                }} else {{
                    document.addEventListener('DOMContentLoaded', initEditor);
                }}
            }})();
        </script>
        """
        return mark_safe(html + init_js)


# ==========================
# Reusable Base Policy Admin
# ==========================
class BasePolicyAdmin(ModelAdmin):
    list_display       = ('get_policy_name', 'get_content_preview', 'last_updated', 'created_at')
    ordering           = ('-last_updated',)
    readonly_fields    = ('last_updated', 'created_at')
    
    fieldsets = (
        ("📄 Policy Document Editor", {
            "fields": ("content",),
            "description": "Use the visual buttons below (Bold, Heading, Lists, Links, etc.) to format your policy document like MS Word."
        }),
        ("🕒 History & Timestamps", {
            "fields": ("created_at", "last_updated"),
            "classes": ("collapse",),
        }),
    )

    formfield_overrides = {
        models.TextField: {
            'widget': RichTextEditorWidget()
        }
    }

    @admin.display(description="Policy Name")
    def get_policy_name(self, obj):
        return obj._meta.verbose_name.title()

    @admin.display(description="Content Preview")
    def get_content_preview(self, obj):
        if not obj.content:
            return "Empty"
        text = obj.content.replace('\n', ' ')
        return text[:80] + ('...' if len(text) > 80 else '')


@admin.register(Privacy_Policy)
class PrivacyPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Terms_Of_Service)
class TermsOfServiceAdmin(BasePolicyAdmin):
    pass


@admin.register(Cookie_Policy)
class CookiePolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(EMI_Payment_Policy)
class EMIPaymentPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Warranty_Policy)
class WarrantyPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Exchange_Policy)
class ExchangePolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Delivery_Policy)
class DeliveryPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(PreOrder_Policy)
class PreOrderPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Refund_Policy)
class RefundPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Return_Policy)
class ReturnPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Seller_Policy)
class SellerPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Buyer_Protection_Policy)
class BuyerProtectionPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Prohibited_Products_Policy)
class ProhibitedProductsPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Intellectual_Property_Policy)
class IntellectualPropertyPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Community_Guidelines)
class CommunityGuidelinesAdmin(BasePolicyAdmin):
    pass


@admin.register(About_Us)
class AboutUsAdmin(BasePolicyAdmin):
    pass

@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display       = ('user', 'rating', 'comment', 'created_at')
    ordering           = ('-created_at',)
    search_fields      = ('user__email', 'rating', 'created_at')
    list_filter        = ('rating', 'created_at')
    readonly_fields    = ('user', 'rating', 'comment', 'created_at')
    list_filter_submit = True

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions