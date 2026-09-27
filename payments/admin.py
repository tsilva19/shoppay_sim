from django.contrib import admin

from .models import Boleto, Installment, PixCharge, PixTransfer, Purchase


@admin.register(PixCharge)
class PixChargeAdmin(admin.ModelAdmin):
    list_display = ("wallet", "amount", "status", "created_at", "expires_at", "paid_at")
    list_filter = ("status",)
    readonly_fields = ("e2e_id", "payload")


@admin.register(PixTransfer)
class PixTransferAdmin(admin.ModelAdmin):
    list_display = ("from_wallet", "to_wallet", "amount", "status", "created_at")
    list_filter = ("status",)
    readonly_fields = ("e2e_id",)


@admin.register(Boleto)
class BoletoAdmin(admin.ModelAdmin):
    list_display = ("payer_wallet", "description", "amount", "due_date", "status")
    list_filter = ("status",)
    readonly_fields = ("barcode",)


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0
    readonly_fields = ("number", "amount", "due_date", "status", "paid_at")
    can_delete = False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("wallet", "merchant", "total_amount", "installments_count", "created_at")
    inlines = [InstallmentInline]


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ("purchase", "number", "amount", "due_date", "status")
    list_filter = ("status",)
