# ShopPay Sim — simulador de carteira digital em Django

Projeto de **estudo local**, sem qualquer integração com uma loja real.
Simula o comportamento de funcionalidades típicas de uma carteira digital
de e-commerce: carteira digital com saldo, PIX (cobrança e transferência),
boleto, carnê digital (compra parcelada) e cashback.

## Arquitetura

- **wallet** — `Wallet` (saldo + chave PIX) e `Transaction` (extrato). Toda
  movimentação de dinheiro no sistema passa por `wallet/services.py`
  (`credit()` / `debit()`), que usa `select_for_update()` dentro de uma
  transação atômica para evitar corrida em saldo concorrente, e levanta
  `InsufficientFundsError` quando não há saldo.
- **payments** — `PixCharge` (cobrança/QR Code), `PixTransfer` (P2P entre
  carteiras), `Boleto`, `Purchase` + `Installment` (carnê digital). Toda regra
  fica em `payments/services.py`; os models só guardam estado.
- **cashback** — `CashbackRule` (regra por % e valor mínimo) e
  `CashbackCredit` (crédito efetivamente aplicado). `apply_cashback()` roda
  automaticamente dentro de `create_purchase()`.
- Uma carteira é criada automaticamente para cada `User` via signal
  (`wallet/signals.py`).
- Todo objeto de origem (PIX, boleto, parcela, cashback) fica ligado à
  `Transaction` correspondente via `GenericForeignKey`, então dá pra rastrear
  a origem de cada linha do extrato.

## Rodando

```bash
cd shoppay_sim
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Acesse:
- `http://127.0.0.1:8000/admin/` — usuário `admin` / senha `admin123`
- `http://127.0.0.1:8000/api/...` — Browsable API do DRF (login em `/api-auth/login/`)

### Usuários de exemplo (criados por `seed_demo`)

| usuário         | senha       | papel                        |
|-----------------|-------------|-------------------------------|
| `thiago`        | thiago123   | cliente com saldo, boleto, carnê |
| `loja_parceira` | loja123     | recebe PIX do thiago          |
| `admin`         | admin123    | superusuário (Django admin)   |

Para recriar os dados de exemplo do zero:

```bash
rm db.sqlite3
python manage.py migrate
python manage.py seed_demo
```

## Endpoints principais

Autenticação: Basic Auth ou sessão (login pelo admin/`/api-auth/login/`).
Todos os endpoints abaixo operam sobre a carteira **do usuário autenticado**.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/wallet/me/` | Saldo e chave PIX da carteira |
| GET | `/api/wallet/transactions/` | Extrato |
| GET/POST | `/api/payments/pix/charges/` | Lista / gera cobrança PIX (`amount`, `description`) |
| POST | `/api/payments/pix/charges/<id>/pay/` | Simula pagamento da cobrança (credita saldo) |
| GET/POST | `/api/payments/pix/transfers/` | Lista / envia PIX (`to_pix_key`, `amount`, `description`) |
| GET/POST | `/api/payments/boletos/` | Lista / emite boleto (`description`, `amount`, `due_date`) |
| POST | `/api/payments/boletos/<id>/pay/` | Paga o boleto (debita saldo) |
| GET/POST | `/api/payments/purchases/` | Lista / cria compra parcelada (`merchant`, `total_amount`, `installments_count`) — já aplica cashback |
| POST | `/api/payments/installments/<id>/pay/` | Paga uma parcela do carnê |
| GET | `/api/cashback/rules/` | Regras de cashback ativas |
| GET | `/api/cashback/credits/` | Cashbacks creditados na carteira |

### Exemplo — adicionar saldo via PIX

```bash
curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/pix/charges/ \
  -H "Content-Type: application/json" \
  -d '{"amount": "200.00", "description": "Adicionar saldo"}'
# -> pega o "id" da resposta

# confirma o pagamento da cobrança (simula o pagador escaneando o QR Code) e credita o saldo na carteira;
# troque o "1" abaixo pelo "id" retornado no passo anterior
curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/pix/charges/1/pay/
```

### Exemplo — comprar parcelado (gera o carnê digital)

```bash
curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/purchases/ \
  -H "Content-Type: application/json" \
  -d '{"merchant": "Loja X", "total_amount": "300.00", "installments_count": 3}'
```

A resposta já vem com as 3 parcelas (vencimento mensal) e, se houver uma
`CashbackRule` ativa cujo mínimo seja atingido, o cashback é creditado na hora
(visível em `/api/cashback/credits/` e no extrato).

## Fluxo completo de teste (todas as rotas)

Sequência sugerida para testar o sistema do zero, na ordem em que os dados
vão se encadeando (cada passo depende do `id`/saldo gerado no anterior).

**1. Ver a carteira (saldo zerado e chave PIX geradas pelo `seed_demo`)**

```bash
curl -u thiago:thiago123 http://127.0.0.1:8000/api/wallet/me/
```

**2. Adicionar saldo via PIX** (cobrança + pagamento — ver seção acima)

**3. Transferir PIX para outra carteira** (`thiago` → `loja_parceira`)

Primeiro pegue a chave PIX de destino (ela é gerada aleatoriamente pelo
`seed_demo`, então não dá pra cravar no curl):

```bash
curl -u loja_parceira:loja123 http://127.0.0.1:8000/api/wallet/me/
# -> pega o "pix_key" da resposta

curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/pix/transfers/ \
  -H "Content-Type: application/json" \
  -d '{"to_pix_key": "<pix_key da loja_parceira>", "amount": "50.00", "description": "Pagamento"}'
```

Debita `thiago` e credita `loja_parceira` na mesma transação; falha se
`thiago` não tiver saldo suficiente (`InsufficientFundsError`).

**4. Emitir e pagar um boleto**

```bash
curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/boletos/ \
  -H "Content-Type: application/json" \
  -d '{"description": "Conta de luz", "amount": "120.00", "due_date": "2026-10-15"}'
# -> pega o "id" da resposta

curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/boletos/1/pay/
```

O pagamento debita o valor da carteira; se `thiago` não tiver saldo, o
endpoint retorna erro (pague o PIX do passo 2 antes, ou use um `amount` menor).

**5. Comprar parcelado (carnê digital) e pagar uma parcela**

```bash
curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/purchases/ \
  -H "Content-Type: application/json" \
  -d '{"merchant": "Loja X", "total_amount": "300.00", "installments_count": 3}'
# -> resposta traz as 3 parcelas; pega o "id" da 1ª parcela em "installments"

curl -u thiago:thiago123 -X POST http://127.0.0.1:8000/api/payments/installments/1/pay/
```

Como o valor (`300.00`) atinge o `min_purchase_amount` da regra padrão criada
pelo `seed_demo` (5% acima de R$50), o cashback é creditado automaticamente
**na criação da compra**, não no pagamento da parcela.

**6. Conferir regras e créditos de cashback**

```bash
curl -u thiago:thiago123 http://127.0.0.1:8000/api/cashback/rules/
curl -u thiago:thiago123 http://127.0.0.1:8000/api/cashback/credits/
```

**7. Ver o extrato consolidado**

```bash
curl -u thiago:thiago123 http://127.0.0.1:8000/api/wallet/transactions/
```

Toda movimentação dos passos anteriores (PIX recebido, PIX enviado, boleto
pago, parcela paga, cashback) aparece aqui, cada linha ligada à origem
correspondente via `GenericForeignKey`.

## O que é simulado (não real)

- Não há integração com Banco Central / PSP: PIX é apenas um registro no
  banco local, com `e2e_id` e `payload` no formato parecido, mas fake.
- Boleto não tem dígito verificador real, é uma string de 47 dígitos gerada
  aleatoriamente.
- "Pagar" um boleto/PIX/parcela é uma chamada direta à API — não existe
  webhook de PSP nem confirmação assíncrona.
- Sem KYC, sem análise de crédito para o carnê — qualquer usuário pode
  parcelar qualquer valor (limitado apenas ao saldo, na hora de pagar cada
  parcela).

## Próximos passos possíveis (se quiser evoluir o estudo)

- Trocar Basic Auth por JWT (`djangorestframework-simplejwt`).
- Adicionar testes automatizados (`pytest-django`) para os `services.py`.
- Simular expiração de boleto/parcela vencida com uma tarefa periódica
  (`django-crontab` ou Celery beat) chamando `refresh_status()`.
- Adicionar limite de crédito por usuário para o carnê digital.
