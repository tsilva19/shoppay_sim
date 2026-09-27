from django.urls import path

from . import views

app_name = "cashback"

urlpatterns = [
    path("rules/", views.CashbackRuleListView.as_view(), name="rule-list"),
    path("credits/", views.MyCashbackCreditsView.as_view(), name="credit-list"),
]
