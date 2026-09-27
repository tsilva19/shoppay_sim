from django.contrib import admin

from .models import Transaction, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "pix_key", "balance", "created_at")
    search_fields = ("user__username", "user__email", "pix_key")
    readonly_fields = ("balance",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "kind", "amount", "balance_after", "description", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("wallet__user__username", "description")
    readonly_fields = ("wallet", "kind", "amount", "balance_after", "description", "content_type", "object_id")
