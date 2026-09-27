from django.contrib import admin

from .models import CashbackCredit, CashbackRule


@admin.register(CashbackRule)
class CashbackRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "percentage", "min_purchase_amount", "active")
    list_filter = ("active",)


@admin.register(CashbackCredit)
class CashbackCreditAdmin(admin.ModelAdmin):
    list_display = ("wallet", "purchase", "rule", "amount", "created_at")
    readonly_fields = ("wallet", "purchase", "rule", "amount")
