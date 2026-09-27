"""Regras de negócio de pagamentos: PIX, boleto e carnê digital (parcelamento)."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta
from django.db import transaction as db_transaction
from django.utils import timezone

from wallet.models import Wallet
from wallet.services import credit, debit

from .models import Boleto, Installment, PixCharge, PixTransfer, Purchase


# ---------------------------------------------------------------------------
# PIX
# ---------------------------------------------------------------------------


def create_pix_charge(wallet: Wallet, amount: Decimal, description: str = "") -> PixCharge:
    """Gera uma cobrança PIX (equivalente a 'gerar QR Code para adicionar saldo')."""
    if amount <= 0:
        raise ValueError("O valor da cobrança PIX deve ser positivo.")
    return PixCharge.objects.create(wallet=wallet, amount=amount, description=description)


@db_transaction.atomic
def pay_pix_charge(charge: PixCharge) -> PixCharge:
    """Simula o pagador escaneando o QR Code: credita o saldo de quem recebe."""
    charge = PixCharge.objects.select_for_update().get(pk=charge.pk)

    if charge.status != PixCharge.Status.PENDING:
        raise ValueError(f"Cobrança PIX já está com status {charge.status}.")
    if charge.expires_at < timezone.now():
        charge.status = PixCharge.Status.EXPIRED
        charge.save(update_fields=["status"])
        raise ValueError("Cobrança PIX expirada.")

    charge.status = PixCharge.Status.PAID
    charge.paid_at = timezone.now()
    charge.save(update_fields=["status", "paid_at"])

    credit(
        charge.wallet,
        charge.amount,
        f"PIX recebido — {charge.description or charge.e2e_id}",
        source=charge,
    )
    return charge


@db_transaction.atomic
def create_pix_transfer(
    from_wallet: Wallet, to_pix_key: str, amount: Decimal, description: str = ""
) -> PixTransfer:
    """Envia um PIX de uma carteira para a chave PIX de outra."""
    if from_wallet.pix_key == to_pix_key:
        raise ValueError("Não é possível transferir para a própria chave PIX.")

    try:
        to_wallet = Wallet.objects.select_for_update().get(pix_key=to_pix_key)
    except Wallet.DoesNotExist as exc:
        raise ValueError("Chave PIX de destino não encontrada.") from exc

    transfer = PixTransfer.objects.create(
        from_wallet=from_wallet,
        to_wallet=to_wallet,
        amount=amount,
        description=description,
        status=PixTransfer.Status.COMPLETED,
    )

    try:
        debit(from_wallet, amount, f"PIX enviado para {to_wallet.pix_key}", source=transfer)
        credit(to_wallet, amount, f"PIX recebido de {from_wallet.pix_key}", source=transfer)
    except Exception:
        transfer.status = PixTransfer.Status.FAILED
        transfer.save(update_fields=["status"])
        raise

    return transfer


# ---------------------------------------------------------------------------
# Boleto
# ---------------------------------------------------------------------------


def create_boleto(
    wallet: Wallet, amount: Decimal, due_date: date, description: str
) -> Boleto:
    if amount <= 0:
        raise ValueError("O valor do boleto deve ser positivo.")
    return Boleto.objects.create(
        payer_wallet=wallet, amount=amount, due_date=due_date, description=description
    )


@db_transaction.atomic
def pay_boleto(boleto: Boleto) -> Boleto:
    boleto = Boleto.objects.select_for_update().get(pk=boleto.pk)
    boleto.refresh_status()

    if boleto.status == Boleto.Status.PAID:
        raise ValueError("Boleto já está pago.")

    debit(boleto.payer_wallet, boleto.amount, f"Pagamento de boleto — {boleto.description}", source=boleto)

    boleto.status = Boleto.Status.PAID
    boleto.paid_at = timezone.now()
    boleto.save(update_fields=["status", "paid_at"])
    return boleto


# ---------------------------------------------------------------------------
# Carnê digital (compra parcelada)
# ---------------------------------------------------------------------------


def _split_amount(total: Decimal, parts: int) -> list[Decimal]:
    """Divide o valor total em N parcelas de centavos exatos (sem perder centavo)."""
    cents_total = int((total * 100).to_integral_value(rounding=ROUND_HALF_UP))
    base, remainder = divmod(cents_total, parts)
    amounts = [Decimal(base) / 100] * parts
    for i in range(remainder):
        amounts[i] += Decimal("0.01")
    return amounts


@db_transaction.atomic
def create_purchase(
    wallet: Wallet, merchant: str, total_amount: Decimal, installments_count: int = 1
) -> Purchase:
    """Registra uma compra e gera o carnê digital (parcelas mensais)."""
    if total_amount <= 0:
        raise ValueError("O valor da compra deve ser positivo.")
    if installments_count < 1:
        raise ValueError("O número de parcelas deve ser >= 1.")

    purchase = Purchase.objects.create(
        wallet=wallet,
        merchant=merchant,
        total_amount=total_amount,
        installments_count=installments_count,
    )

    amounts = _split_amount(total_amount, installments_count)
    today = timezone.localdate()
    installments = [
        Installment(
            purchase=purchase,
            number=i + 1,
            amount=amounts[i],
            due_date=today + relativedelta(months=i + 1),
        )
        for i in range(installments_count)
    ]
    Installment.objects.bulk_create(installments)

    # Cashback é aplicado sobre a compra inteira, no momento da compra
    from cashback.services import apply_cashback

    apply_cashback(purchase)

    return purchase


@db_transaction.atomic
def pay_installment(installment: Installment) -> Installment:
    installment = Installment.objects.select_for_update().get(pk=installment.pk)
    installment.refresh_status()

    if installment.status == Installment.Status.PAID:
        raise ValueError("Parcela já está paga.")

    wallet = installment.purchase.wallet
    debit(
        wallet,
        installment.amount,
        f"Parcela {installment.number}/{installment.purchase.installments_count} — {installment.purchase.merchant}",
        source=installment,
    )

    installment.status = Installment.Status.PAID
    installment.paid_at = timezone.now()
    installment.save(update_fields=["status", "paid_at"])
    return installment
