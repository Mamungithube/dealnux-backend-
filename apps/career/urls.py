from django.urls import path
from .views import (
    CareerApplicationCreateView,
    CareerApplicationListView,
    CareerRoleListView,
)

urlpatterns = [
    path('roles/', CareerRoleListView.as_view(), name='career-roles'),
    path('apply/', CareerApplicationCreateView.as_view(), name='career-apply'),
    path('applications/', CareerApplicationListView.as_view(), name='career-applications'),
]