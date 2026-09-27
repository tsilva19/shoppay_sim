# ShopPay Sim — guia de estudo técnico (Python + Django + DRF)

Este documento existe para **estudar o projeto**, não para operá-lo (isso já
está no `README.md`). A ideia é abrir os dois lado a lado: o README diz *o
que* a API faz; este arquivo explica *como* e *por quê* cada peça do Django
foi usada, do arquivo de configuração até a regra de negócio final.

---

## 1. Mapa mental — visão geral

```
shoppay_sim (projeto Django)
│
├── settings.py ─────────────► configura TUDO: apps, banco, auth, DRF
├── urls.py (raiz) ──────────► distribui /api/* para cada app
│
├── wallet/            (a "conta" — dono do dinheiro)
│   ├── models.py       → Wallet, Transaction
│   ├── signals.py       → cria Wallet quando um User é criado
│   ├── services.py      → credit() / debit() — ÚNICO lugar que mexe em saldo
│   ├── serializers.py + views.py + urls.py → API somente leitura
│
├── payments/           (as "operações" — o que gera crédito/débito)
│   ├── models.py       → PixCharge, PixTransfer, Boleto, Purchase, Installment
│   ├── services.py      → regra de negócio de cada operação
│   │                       (chama wallet.services.credit/debit por baixo)
│   ├── serializers.py + views.py + urls.py → API de leitura/escrita
│   └── management/commands/seed_demo.py → popula dados de teste
│
└── cashback/            (uma "regra" que reage a uma compra)
    ├── models.py        → CashbackRule, CashbackCredit
    ├── services.py       → apply_cashback() — chamado de dentro de
    │                        payments.services.create_purchase()
    └── serializers.py + views.py + urls.py → API somente leitura
```

Ideia central para gravar: **models guardam estado, services decidem o que
pode acontecer com esse estado, views só traduzem HTTP ⇄ services**. É a
espinha dorsal do projeto inteiro — quase toda dúvida sobre "onde eu mexo
para mudar tal comportamento" se responde localizando o `services.py` certo.

---

## 2. Configuração (`shoppay_sim/settings.py`)

Um projeto Django é, na prática, um dicionário gigante de configurações lido
por todo o resto do framework. Pontos relevantes deste projeto:

- **`INSTALLED_APPS`** — lista de apps que o Django "liga". Além dos apps
  nativos (`admin`, `auth`, `contenttypes`, `sessions`, ...), aparecem
  `rest_framework` (Django REST Framework) e os três apps do projeto
  (`wallet`, `payments`, `cashback`). Um app só participa de migrations,
  admin e templates se estiver aqui.
- **`REST_FRAMEWORK`** — configuração global do DRF:
  - `DEFAULT_AUTHENTICATION_CLASSES`: aceita login por **sessão** (cookie,
    usado pela Browsable API/`/api-auth/login/`) ou **Basic Auth**
    (usuário:senha em cada request — é o que os `curl -u` do README usam).
  - `DEFAULT_PERMISSION_CLASSES`: `IsAuthenticated` — **toda** rota exige
    login por padrão, mesmo sem declarar `permission_classes` em cada view.
- **`MIDDLEWARE`** — pipeline por onde toda request passa antes de chegar na
  view (sessão, CSRF, autenticação, etc.), na ordem em que aparece na lista.
- **`ROOT_URLCONF = "shoppay_sim.urls"`** — diz ao Django onde está o
  arquivo de rotas raiz.
- **`DATABASES`** — SQLite em arquivo local (`db.sqlite3`). Zero setup, mas
  sem suporte real a concorrência pesada — ok para estudo, não para produção.
- **`AUTH_PASSWORD_VALIDATORS`** — regras aplicadas quando um usuário troca
  de senha via Django (tamanho mínimo, não ser só números, etc.). Não afeta
  `set_password()` chamado direto no `seed_demo.py` (validação só roda em
  formulários/serializers que a chamam explicitamente).
- **`LANGUAGE_CODE = "pt-br"` / `TIME_ZONE = "America/Sao_Paulo"` /
  `USE_TZ = True`** — Django guarda datas em UTC no banco e converte para
  este timezone na exibição; é por isso que `timezone.now()` (aware) é usado
  em vez de `datetime.now()` (naive) em todo o código de negócio.
- **`DEFAULT_AUTO_FIELD = "BigAutoField"`** — toda PK sem `id` explícito vira
  um inteiro 64 bits autoincrementado.
- **`SECRET_KEY` fixa e `DEBUG = True`** — assinado como "insecure" pelo
  próprio `startproject`; serve só para dev local (assinatura de sessão/CSRF
  e páginas de erro detalhadas — nunca subir assim para produção).

`manage.py` é só um atalho de linha de comando que injeta
`DJANGO_SETTINGS_MODULE=shoppay_sim.settings` e chama o Django
(`runserver`, `migrate`, `makemigrations`, `createsuperuser`, comandos
customizados como `seed_demo`, etc.). `wsgi.py`/`asgi.py` são os pontos de
entrada que um servidor de produção (gunicorn/uvicorn) usaria — no dia a dia
de estudo, quem chama isso é o próprio `runserver`.

---

## 3. Apps Django — por que três apps e não um só

Cada pasta com `apps.py` + `models.py` é um **app Django**: uma unidade
reutilizável de funcionalidade. Separar em `wallet` / `payments` /
`cashback` segue responsabilidade única:

| App | Responsabilidade | Não sabe sobre |
|---|---|---|
| `wallet` | Ter saldo e registrar extrato | PIX, boleto, parcelas |
| `payments` | Regras de PIX/boleto/carnê | Cashback |
| `cashback` | Aplicar % sobre uma compra | Como o boleto/PIX funcionam |

Só `payments` importa de `wallet` (usa `credit`/`debit`), e só `cashback`
importa de `payments` (lê `Purchase`). `wallet` não importa nada dos outros
dois — é a base da pirâmide. Essa direção única de dependência evita import
circular e deixa claro quem pode quebrar o quê.

`AppConfig.ready()` (em `wallet/apps.py`) é o gancho oficial do Django para
rodar código de inicialização de um app — aqui é usado só para **importar
`signals.py`**, o que registra o `@receiver` (ver seção 5). Sem isso, o
sinal existiria no arquivo mas nunca seria conectado, porque nada mais
importa `wallet.signals` diretamente.

---

## 4. Dados e modelagem (`models.py` de cada app)

Um `models.Model` do Django é, ao mesmo tempo: (1) uma classe Python comum,
com métodos e `__str__`; e (2) uma declaração de tabela SQL — cada atributo
de classe vira uma coluna. É a materialização do padrão **ActiveRecord** +
ORM.

Conceitos usados neste projeto, com onde aparecem:

- **Relacionamentos**
  - `OneToOneField` (`Wallet.user`) — 1 usuário = 1 carteira, exatamente.
  - `ForeignKey` (`Transaction.wallet`, `PixCharge.wallet`,
    `Installment.purchase`, ...) — N-para-1, com `related_name` definindo o
    acessor reverso (ex.: `wallet.transactions.all()`,
    `purchase.installments.all()`).
  - `on_delete=models.CASCADE` — apaga os "filhos" se o "pai" for apagado
    (ex.: apagar uma `Purchase` apaga suas `Installment`s).
  - `on_delete=models.SET_NULL` (`Transaction.content_type`,
    `CashbackCredit.rule`) — em vez de apagar em cascata, zera a referência;
    exige `null=True` no campo.
- **`GenericForeignKey`** (`Transaction.source`, em `wallet/models.py`) —
  uma FK "polimórfica": em vez de apontar para uma tabela fixa, guarda o
  tipo (`content_type`, via `django.contrib.contenttypes`) + o id
  (`object_id`) do objeto de origem, que pode ser um `PixCharge`, um
  `Boleto`, uma `Installment` ou um `CashbackCredit`. É o que permite o
  extrato dizer "esta linha veio *daquele* pagamento específico" sem a
  tabela `Transaction` precisar de uma FK para cada tipo de operação.
- **`models.TextChoices`** (`Transaction.Kind`, `PixCharge.Status`,
  `Boleto.Status`, `Installment.Status`, `PixTransfer.Status`) — enum
  tipado do Django: gera automaticamente `.choices` (para o campo),
  `.CREDIT`/`.PENDING`/etc. (constantes usáveis em Python) e um método
  `get_<campo>_display()` (ex.: `charge.get_status_display()` retorna
  "Aguardando pagamento" em vez de `"PENDING"`).
- **`DecimalField(max_digits=12, decimal_places=2)`** para **todo** valor
  monetário — nunca `FloatField`. Ponto crucial: `float` tem erro de
  arredondamento binário (`0.1 + 0.2 != 0.3`), inaceitável para dinheiro;
  `Decimal` é aritmética decimal exata. Em Python, o código de negócio
  sempre recebe/retorna `Decimal` (ver `services.py` de cada app).
- **Valores default via função** (`default=generate_pix_key`,
  `default=generate_e2e_id`, `default=generate_barcode`) — o Django chama a
  função **sem argumentos** a cada novo registro (diferente de
  `default=generate_pix_key()`, que executaria uma única vez, no
  carregamento do módulo, e repetiria o mesmo valor para todo mundo — um erro
  clássico de configuração).
- **`auto_now_add=True`** (`created_at`) — preenchido uma única vez, na
  criação, pelo próprio Django; não é editável depois.
- **Override de `save()`** (`PixCharge.save`) — antes de persistir, se
  `expires_at`/`payload` não vieram preenchidos, calcula um valor default
  "dinâmico" (30 minutos a partir de agora, ou uma string derivada do
  `e2e_id`). Sempre termina chamando `super().save(*args, **kwargs)` para
  não quebrar o comportamento padrão do ORM.
- **Métodos de instância que mudam estado** (`Boleto.refresh_status`,
  `Installment.refresh_status`) — leem `timezone.localdate()` e, se venceu
  sem ter sido pago, promovem o status para `OVERDUE` e salvam. Note que
  isso é **lazy**: só roda quando alguém chama `refresh_status()` (hoje,
  dentro de `pay_boleto`/`pay_installment`, antes de checar se já está
  pago) — não existe um job de fundo mudando status sozinho (ver seção 9,
  gaps).
- **`class Meta`** — metadados que não viram coluna: `ordering` (ordem
  default das queries, ex. `Transaction` mais recente primeiro),
  `unique_together` (`Installment`: não pode haver duas parcelas com o
  mesmo número na mesma compra — constraint garantida pelo banco).
- **`__str__`** — não é "só estético": é o que aparece no Django Admin, em
  `repr()` de debug e em qualquer `f"{objeto}"`.

### Migrations — a ponte entre model Python e tabela SQL

`python manage.py makemigrations` **compara** o estado atual dos
`models.py` com o "histórico" gravado em `*/migrations/000X_*.py` e gera um
novo arquivo Python descrevendo a diferença (`CreateModel`, `AddField`,
`AlterField`...). `python manage.py migrate` **aplica** essas migrations
pendentes no banco (executa o SQL equivalente) e registra o que já rodou na
tabela `django_migrations`. Ou seja: **os arquivos em `migrations/` são a
fonte da verdade do schema**, não o `models.py` sozinho — por isso o projeto
tem `0001_initial.py`/`0002_initial.py` versionados em `wallet/`,
`payments/`/`cashback`.

---

## 5. Sinais (`wallet/signals.py`)

```python
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_wallet_for_new_user(sender, instance, created, **kwargs):
    if created:
        Wallet.objects.create(user=instance, pix_key=generate_pix_key())
```

`post_save` é um **evento** disparado pelo Django toda vez que `.save()` é
chamado em qualquer model — aqui, especificamente em `User`
(`settings.AUTH_USER_MODEL` evita hardcodar `django.contrib.auth.User`,
para funcionar mesmo se o projeto trocasse de user model). O decorator
`@receiver` inscreve a função como "ouvinte" desse evento. `created` é um
booleano que distingue "acabou de nascer" de "só foi atualizado" — sem esse
`if`, toda vez que um `User` fosse salvo (ex.: trocar de senha) o sistema
tentaria criar outra carteira e quebraria por causa do `OneToOneField`
(unicidade).

Por que sinal em vez de criar a `Wallet` manualmente na view de cadastro?
Porque **nenhuma view de cadastro de usuário existe neste projeto** (usuários
são criados via admin/`seed_demo`/shell) — o sinal garante a invariante
"todo `User` tem uma `Wallet`" **não importa por onde** o `User` seja criado,
sem duplicar essa lógica em vários lugares.

---

## 6. Camada de serviços (`services.py`) — o coração do projeto

Esta é a decisão de arquitetura mais importante do projeto, e a que mais
vale entender bem: **regra de negócio não mora nem no model, nem na view —
mora numa função de `services.py`.**

### 6.1 Por que não colocar a lógica na view?

Views devem só traduzir HTTP: ler request, validar formato (serializer),
chamar a regra de negócio, devolver Response/status code. Se a regra
("debitar exige saldo", "cobrança expira em 30min", "cashback é a melhor
regra ativa") estivesse espalhada pelas views, ela não poderia ser chamada a
partir de outro lugar (ex.: `seed_demo.py` chama
`payments_services.create_pix_charge` e `pay_pix_charge` diretamente, sem
passar por HTTP nenhum) nem testada sem simular uma request inteira.

### 6.2 Por que não colocar tudo no model?

Um pouco de lógica *fica* no model quando é sobre o próprio objeto isolado
(`Boleto.refresh_status`, `PixCharge.save`). Mas assim que a operação
envolve **mais de um objeto** e precisa ser **atômica** (ex.: `pay_pix_charge`
muda o status da cobrança **e** credita a carteira **e** cria uma
`Transaction` — as três coisas têm que acontecer juntas ou nenhuma), colocar
isso num método de model tornaria o model "gordo" e escondido — a função de
serviço deixa explícito, no nome, qual é a operação de negócio completa.

### 6.3 `@transaction.atomic` — tudo ou nada

```python
@db_transaction.atomic
def pay_pix_charge(charge: PixCharge) -> PixCharge:
    ...
```

Envolve a função inteira numa transação de banco: se qualquer linha depois
do decorator levantar uma exceção, **todo** o trabalho feito até ali dentro
da função é desfeito (`ROLLBACK`) — não existe estado parcial (ex.: cobrança
marcada como paga mas saldo não creditado, porque o `credit()` no meio do
caminho falhou).

### 6.4 `select_for_update()` — travar a linha certa

```python
wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
```

Dentro de uma transação atômica, isso pede ao banco um **lock pessimista**
na linha da carteira: se duas requisições tentarem debitar/creditar a mesma
carteira ao mesmo tempo, a segunda **espera** a primeira transação terminar
(commit ou rollback) antes de ler o saldo. Sem isso, duas requisições
concorrentes poderiam ler o mesmo saldo inicial, cada uma decidir "tem saldo
suficiente" e ambas debitarem — deixando a carteira negativa (uma *race
condition* clássica de sistemas financeiros). É por isso que **toda**
alteração de saldo (`credit`/`debit` em `wallet/services.py`, e as leituras
de `PixCharge`/`Boleto`/`Installment` antes de pagar) usa esse padrão.

### 6.5 Exceções de negócio dedicadas

```python
class InsufficientFundsError(Exception): ...
```

Em vez de estourar uma exceção genérica do Django/Python, o domínio define
sua própria classe. As views capturam especificamente
`(ValueError, InsufficientFundsError)` e traduzem para
`rest_framework.exceptions.ValidationError` (HTTP 400) — a camada HTTP só
conhece "isso é um erro de validação", sem precisar saber os detalhes de
saldo/regra por trás.

### 6.6 Composição entre serviços de apps diferentes

`payments.services.create_purchase()` termina chamando
`cashback.services.apply_cashback(purchase)` — repare que o `import` está
**dentro da função**, não no topo do arquivo:

```python
def create_purchase(...):
    ...
    from cashback.services import apply_cashback
    apply_cashback(purchase)
```

Isso evita import circular: `cashback/models.py` importa
`payments.models.Purchase` (para a FK de `CashbackCredit`), então se
`payments/services.py` importasse `cashback` no topo do arquivo, ao carregar
o Python entraria num ciclo. Adiar o `import` para dentro da função resolve
isso porque, nesse ponto, os dois módulos já terminaram de carregar.

### 6.7 Outros detalhes de services que valem notar

- `_split_amount` (`payments/services.py`) divide o valor total em N
  parcelas **sem perder centavo**: converte para inteiro de centavos,
  distribui o resto (`remainder`) nas primeiras parcelas. Isso evita o bug
  clássico de `total / n` gerar parcelas que, somadas, não batem com o
  total por causa de arredondamento.
- `relativedelta(months=i + 1)` (biblioteca `python-dateutil`, a única
  dependência externa além de Django/DRF) — soma meses de forma calendárica
  correta (ex.: 31/01 + 1 mês vira 28/02, não "31 dias depois").

---

## 7. Camada de API (Django REST Framework)

### 7.1 Serializers — validação de entrada e formato de saída

Dois padrões usados lado a lado:

- **`ModelSerializer`** (`PixChargeSerializer`, `BoletoSerializer`, ...) —
  gera campos automaticamente a partir do model; usado para **serializar
  saída** (`Response`). `read_only_fields` trava campos que existem no
  model mas não devem vir do cliente (ex.: `status`, `paid_at`, `barcode` —
  são decididos pelo servidor).
- **`Serializer` puro** (`PixChargeCreateSerializer`,
  `PixTransferCreateSerializer`) — usado só para **validar entrada** de um
  `POST`, quando o formato de entrada não bate 1:1 com o model (ex.:
  `PixTransferCreateSerializer` recebe `to_pix_key`, um campo que não existe
  em `PixTransfer` — o model tem `to_wallet`, uma FK; é o
  `service`/`view` que resolve a chave PIX para uma `Wallet` de fato).

`SerializerMethodField` (`TransactionSerializer.source_type`,
`CashbackCreditSerializer` via `source="purchase.merchant"`) permite expor
um valor calculado/derivado (aqui, o nome do model de origem via
`content_type.model`) que não é uma coluna direta.

### 7.2 Views — `APIView` vs `generics.*`

- **`generics.ListCreateAPIView`** (`PixChargeListCreateView`,
  `PixTransferListCreateView`, `PurchaseListCreateView`) — implementa GET
  (lista) e POST (cria) praticamente de graça; só é preciso sobrescrever
  `get_queryset()` (filtrar pela carteira do usuário logado — **nunca**
  listar tudo de todo mundo) e, quando o `create()` padrão não serve porque
  a criação precisa passar por um `service` em vez de `serializer.save()`
  direto, sobrescrever `create()` também.
- **`generics.ListAPIView`** (`MyTransactionsView`, `CashbackRuleListView`,
  `MyCashbackCreditsView`) — só leitura em lista.
- **`APIView`** puro (`MyWalletView`, `PixChargePayView`, `BoletoPayView`,
  `InstallmentPayView`) — usado quando a ação não é "CRUD de uma lista",
  e sim uma ação pontual (`GET` de um único objeto derivado do usuário
  logado, ou `POST .../pay/` que não cria nem lista nada, só dispara uma
  transição de estado). Cada verbo HTTP vira um método (`get`, `post`).

Padrão repetido em todo `get_queryset()`/`get_object_or_404(...,
wallet=_wallet(request))`: **toda query já nasce filtrada pelo dono
(`request.user`)** — é a forma deste projeto de garantir que um usuário
nunca veja/pague operação de outro usuário (equivalente a um controle de
autorização por objeto, feito na mão em vez de usar um framework de
permissões por objeto).

### 7.3 Urls — roteamento em duas camadas

```python
# shoppay_sim/urls.py (raiz)
path("api/payments/", include("payments.urls")),

# payments/urls.py
app_name = "payments"
urlpatterns = [
    path("pix/charges/<int:pk>/pay/", views.PixChargePayView.as_view(), name="pix-charge-pay"),
    ...
]
```

`include()` delega tudo que casar com o prefixo `api/payments/` para o
`urls.py` do app, que só cuida do sufixo. `app_name` cria um *namespace*
(permite usar `reverse("payments:pix-charge-pay", args=[id])` em vez de
montar a URL na mão, embora este projeto não use `reverse()` explicitamente
em runtime). `<int:pk>` é um *path converter*: casa só dígitos e já entrega
`pk` como `int` para a view — se alguém chamar `/pix/charges/abc/pay/`, o
Django devolve 404 antes mesmo de a view rodar.

### 7.4 Autenticação e autorização, na prática

`IsAuthenticated` (global, em `settings.py`) barra qualquer request sem
credencial válida (401). A partir daí, **não existe um sistema de
permissões por papel** (ex.: "admin pode tudo") — a única regra de
autorização é implícita: cada view só opera sobre `request.user.wallet`
(o acessor reverso do `OneToOneField` criado em `wallet/models.py`). Isso é
suficiente para o escopo do projeto (cada usuário só vê a própria carteira),
mas é uma simplificação — não há, por exemplo, papel de "operador" que veja
carteiras de terceiros.

---

## 8. Admin (`admin.py` de cada app)

O Django Admin é gerado automaticamente a partir do `ModelAdmin` registrado:

- `list_display` — colunas na listagem.
- `list_filter` — filtros na barra lateral.
- `search_fields` — habilita a busca (`user__username` mostra que dá para
  buscar por campo de relação, atravessando o `ForeignKey`).
- `readonly_fields` — campos visíveis mas não editáveis pela tela (ex.:
  `balance` só pode mudar via `credit`/`debit`, nunca editando a carteira
  direto no admin — mantém a regra de negócio como única porta de entrada
  para mudar saldo).
- `TabularInline` (`InstallmentInline`, dentro de `PurchaseAdmin`) — mostra
  as parcelas de uma compra **dentro** da própria tela da compra, sem
  precisar navegar para outra tela.

O admin é, essencialmente, uma segunda "view" sobre os mesmos models — mas
sem passar pelos `services.py`. É uma porta separada, pensada para
administração manual (ex.: cadastrar uma `CashbackRule` nova).

---

## 9. Management command (`seed_demo.py`)

`BaseCommand` é a classe base do Django para comandos de
`python manage.py <nome>`. `handle()` é o método chamado quando o comando
roda. Pontos didáticos aqui:

- `User.objects.get_or_create(...)` — idempotente: rodar `seed_demo` duas
  vezes não duplica usuários.
- O comando **não** insere dados direto via `Model.objects.create(...)`
  para as operações de negócio — ele chama `payments_services.*` e
  `cashback.services.apply_cashback`, os mesmos serviços que a API usa. Isso
  garante que os dados de exemplo respeitam as mesmas regras (saldo
  suficiente, cashback automático, etc.) que qualquer request real
  respeitaria — o seed é só "mais um cliente" da camada de serviço.

---

## 10. Fluxo ponta a ponta (exemplo: pagar uma cobrança PIX)

```
curl POST /api/payments/pix/charges/1/pay/
        │
        ▼
shoppay_sim/urls.py  → casa "api/payments/" → delega para payments/urls.py
        │
        ▼
payments/urls.py     → casa "pix/charges/<pk>/pay/" → PixChargePayView
        │
        ▼
PixChargePayView.post(request, pk)
        │  get_object_or_404(PixCharge, pk=pk, wallet=_wallet(request))
        │  ── já filtra pela carteira do usuário logado
        ▼
services.pay_pix_charge(charge)          [@transaction.atomic]
        │  1. select_for_update() na PixCharge (trava a linha)
        │  2. valida status == PENDING e não expirou
        │  3. charge.status = PAID; charge.save()
        │  4. wallet.services.credit(wallet, amount, ...)
        │        │  select_for_update() na Wallet (trava a linha)
        │        │  wallet.balance += amount; wallet.save()
        │        │  Transaction.objects.create(kind=CREDIT, source=charge)
        ▼
PixChargeSerializer(charge).data  → Response 200 (JSON)
```

Se qualquer passo dentro do bloco atômico falhar (ex.: cobrança já paga,
levanta `ValueError`), o Django desfaz **tudo** dentro da transação e a
view converte a exceção em `ValidationError` → HTTP 400. Nenhum passo
intermediário fica "meio aplicado" no banco.

---

## 11. Conceitos de Python usados (não específicos do Django)

- **Type hints** (`def credit(wallet: Wallet, amount: Decimal, ...) -> Transaction`)
  — documentam o contrato da função; o Python não impõe em runtime, mas
  ajudam leitura/autocomplete/checagem estática (ex.: mypy, se fosse
  configurado — hoje não há checagem de tipos automatizada no projeto).
- **Decorators** (`@receiver`, `@db_transaction.atomic`, `@admin.register`)
  — funções que envolvem outra função/classe para adicionar comportamento
  sem alterar seu código (registrar um listener, abrir uma transação,
  registrar uma classe no admin).
- **`class Foo(models.TextChoices)`** — um enum declarado como classe
  aninhada é um padrão comum em Django para manter as opções de um campo
  coladas ao model que as usa (`PixCharge.Status.PENDING` em vez de uma
  string solta `"PENDING"` espalhada pelo código).
- **List comprehension** (`_split_amount`, `Installment(...) for i in
  range(installments_count)`) — construção de listas em uma linha,
  idiomática em Python.
- **Exceptions customizadas como parte da API do módulo**
  (`InsufficientFundsError`) — em vez de devolver `None`/código de erro,
  o serviço "fala" com quem chamou através do tipo da exceção.
- **`Decimal` em vez de `float`** — já coberto na seção 4, mas vale como
  regra geral de Python para qualquer projeto que lide com dinheiro.
- **f-strings** (`f"Cobrança PIX já está com status {charge.status}."`) —
  usadas para montar toda mensagem de erro/descrição do projeto.

---

## 12. O que falta / simplificações conscientes (gaps a saber que existem)

Isso não está implementado — e vale reconhecer isso para não presumir mais
robustez do que o projeto tem:

- **Sem testes automatizados de verdade** — `wallet/tests.py`,
  `payments/tests.py` e `cashback/tests.py` existem só com o boilerplate do
  `startapp` (`# Create your tests here.`), vazios. O próprio README já
  lista "adicionar testes com pytest-django" como próximo passo.
- **Sem expiração/vencimento automático em background** —
  `PixCharge`/`Boleto`/`Installment` só mudam para `EXPIRED`/`OVERDUE`
  quando alguém tenta *pagar* depois do prazo (checagem síncrona dentro do
  próprio `pay_*`/`refresh_status`); não existe uma tarefa periódica
  (Celery beat, `django-crontab`, cronjob) rodando isso sozinha — também já
  listado como possível próximo passo no README.
- **Sem paginação configurada no DRF** — listas (`GET
  /api/payments/purchases/`, `/api/wallet/transactions/`, etc.) devolvem
  **todos** os registros de uma vez; em produção isso precisaria de
  `DEFAULT_PAGINATION_CLASS` no `REST_FRAMEWORK` do `settings.py`.
- **Sem throttling/rate limiting** — nada limita quantas vezes um usuário
  autenticado pode chamar `.../pay/` por segundo.
- **`SECRET_KEY` fixa no repositório e `DEBUG = True`** — adequado para
  estudo local, mas são os dois primeiros itens do checklist de deploy do
  próprio Django que precisariam mudar (secret via variável de ambiente,
  `DEBUG = False` + `ALLOWED_HOSTS` real) antes de qualquer coisa parecida
  com produção.
- **Autenticação só por sessão/Basic Auth** — sem JWT/OAuth; também já
  citado no README como evolução possível.
- **Sem validação de limite de crédito no carnê** — qualquer usuário pode
  parcelar qualquer valor; o único limite real aparece na hora de *pagar*
  cada parcela (checagem de saldo em `debit()`).
- **PIX/boleto são só simulações locais** — sem integração com Banco
  Central/PSP real, sem dígito verificador de boleto de verdade (já
  descrito no README, seção "O que é simulado").

---

## 13. Glossário rápido

| Termo | Significado neste projeto |
|---|---|
| **ORM** | Camada do Django que traduz classes Python (`models.Model`) em tabelas/queries SQL |
| **Migration** | Arquivo Python versionado que descreve uma mudança incremental de schema |
| **Serializer** | Classe DRF que valida dados de entrada e formata dados de saída em JSON |
| **`select_for_update()`** | Lock pessimista de linha no banco, dentro de uma transação |
| **`transaction.atomic`** | Bloco "tudo ou nada": commit só se nada dentro dele levantar exceção |
| **`GenericForeignKey`** | FK que aponta para "qualquer model", via tabela `ContentType` + id |
| **`TextChoices`** | Enum do Django para campos `choices=` com strings |
| **`related_name`** | Nome do acessor reverso de uma FK/O2O (ex.: `wallet.transactions`) |
| **Service layer** | Camada de funções (`services.py`) que concentra regra de negócio, fora de views/models |
| **`AppConfig.ready()`** | Gancho de inicialização de um app Django (usado aqui para registrar signals) |
