# utils/admin_permissions.py
# এই file টা যেকোনো app এ রাখতে পারো, যেমন: dealnux/admin_permissions.py


def is_manager(user):
    return user.is_superuser


def is_admin_only(user):
    return user.is_staff and not user.is_superuser


class ManagerOnlyMixin:
    """
    শুধু Manager (superuser) access পাবে।
    Admin panel-এ financial ও seller approval sections এ এটা use করো।
    
    Usage:
        class PaymentAdmin(ManagerOnlyMixin, ModelAdmin):
            ...
    """

    def has_module_perms(self, request):
        return is_manager(request.user)

    def has_view_permission(self, request, obj=None):
        return is_manager(request.user)

    def has_add_permission(self, request):
        return is_manager(request.user)

    def has_change_permission(self, request, obj=None):
        return is_manager(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_manager(request.user)


class AdminReadOnlyFinancialMixin:
    """
    Admin শুধু read করতে পারবে financial data,
    Manager full control পাবে।
    
    Usage:
        class PaymentAdmin(AdminReadOnlyFinancialMixin, ModelAdmin):
            ...
    """

    def has_add_permission(self, request):
        return is_manager(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_manager(request.user)

    def has_change_permission(self, request, obj=None):
        return is_manager(request.user)

    def has_view_permission(self, request, obj=None):
        # Admin view করতে পারবে, কিন্তু edit না
        return request.user.is_staff