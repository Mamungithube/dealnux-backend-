from django.urls import path
from .views import CareerApplicationCreateView, CareerApplicationListView

urlpatterns = [
    path('apply/', CareerApplicationCreateView.as_view(), name='career-apply'),
    path('applications/', CareerApplicationListView.as_view(), name='career-applications'),
]