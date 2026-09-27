"""Regras de negócio da carteira: todo dinheiro que entra ou sai passa por aqui."""

from decimal import Decimal

from django.db import transaction as db_transaction

from .models import Transaction, Wallet


class InsufficientFundsError(Exception):
    """Levantado quando a carteira não tem saldo suficiente para um débito."""


@db_transaction.atomic
def credit(
    wallet: Wallet, amount: Decimal, description: str, source=None
) -> Transaction:
    if amount <= 0:
        raise ValueError("O valor do crédito deve ser positivo.")

    # select_for_update evita condição de corrida em créditos concorrentes
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    wallet.balance += amount
    wallet.save(update_fields=["balance"])

    return Transaction.objects.create(
        wallet=wallet,
        kind=Transaction.Kind.CREDIT,
        amount=amount,
        balance_after=wallet.balance,
        description=description,
        source=source,
    )


@db_transaction.atomic
def debit(
    wallet: Wallet, amount: Decimal, description: str, source=None
) -> Transaction:
    if amount <= 0:
        raise ValueError("O valor do débito deve ser positivo.")

    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    if wallet.balance < amount:
        raise InsufficientFundsError(
            f"Saldo insuficiente: disponível R$ {wallet.balance}, necessário R$ {amount}"
        )

    wallet.balance -= amount
    wallet.save(update_fields=["balance"])

    return Transaction.objects.create(
        wallet=wallet,
        kind=Transaction.Kind.DEBIT,
        amount=amount,
        balance_after=wallet.balance,
        description=description,
        source=source,
    )
