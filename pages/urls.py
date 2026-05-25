from django.urls import path
from .views import PressCoverageListView

urlpatterns = [
    path('', PressCoverageListView.as_view(), name='press-list'),
]