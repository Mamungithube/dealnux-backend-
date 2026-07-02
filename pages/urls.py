from django.urls import path
from .views import PressCoverageListView,PressInquiryCreateView

urlpatterns = [
    path('PressCoverage', PressCoverageListView.as_view(), name='press-list'),
    path('press-inquiry', PressInquiryCreateView.as_view(), name='press-inquiry'),
]