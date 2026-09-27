"""Motor de cashback: aplica a melhor regra ativa elegível a cada compra."""

from django.db import transaction as db_transaction

from payments.models import Purchase
from wallet.services import credit

from .models import CashbackCredit, CashbackRule


def _best_rule_for(amount) -> CashbackRule | None:
    """Entre as regras ativas cujo mínimo é atingido, pega a de maior percentual."""
    return (
        CashbackRule.objects.filter(active=True, min_purchase_amount__lte=amount)
        .order_by("-percentage")
        .first()
    )


@db_transaction.atomic
def apply_cashback(purchase: Purchase) -> CashbackCredit | None:
    rule = _best_rule_for(purchase.total_amount)
    if rule is None:
        return None

    amount = (purchase.total_amount * rule.percentage / 100).quantize(
        purchase.total_amount
    )
    if amount <= 0:
        return None

    cashback_credit = CashbackCredit.objects.create(
        wallet=purchase.wallet,
        purchase=purchase,
        rule=rule,
        amount=amount,
    )

    credit(
        purchase.wallet,
        amount,
        f"Cashback ({rule.percentage}%) — {purchase.merchant}",
        source=cashback_credit,
    )

    return cashback_credit
