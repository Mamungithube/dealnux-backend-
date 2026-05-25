from django.urls import path
from .views import PressCoverageListView

urlpatterns = [
    path('PressCoverage', PressCoverageListView.as_view(), name='press-list'),
]