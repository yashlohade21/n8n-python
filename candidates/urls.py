from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'candidates', views.CandidateViewSet, basename='candidate')

urlpatterns = [
    path('health/', views.health_check, name='health-check'),
    path('candidates/upload/', views.upload_cv, name='upload-cv'),
    path('', include(router.urls)),
]
