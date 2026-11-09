from django.conf import settings
from django.db import models
from django.utils import timezone

class Conta(models.Model):
    nome = models.CharField(max_length=150)
    criada_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome

class Membership(models.Model):
    class Papel(models.TextChoices):
        OWNER = "OWNER", "Owner"
        ADMIN = "ADMIN", "Admin"
        MEMBER = "MEMBER", "Member"

    conta = models.ForeignKey(Conta, on_delete=models.CASCADE, related_name="memberships")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    papel = models.CharField(max_length=10, choices=Papel.choices, default=Papel.MEMBER)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("conta", "usuario")

    def __str__(self):
        return f"{self.usuario} -> {self.conta} ({self.papel})"

class Empresa(models.Model):
    conta = models.ForeignKey(
        "core.Conta",
        on_delete=models.CASCADE,
        related_name="empresas"
    )

    cnpj = models.CharField(max_length=14)
    razao_social = models.CharField(max_length=200)
    nome_fantasia = models.CharField(max_length=200, blank=True, default="")

    inscricao_estadual = models.CharField(max_length=30, blank=True, default="")

    class RegimeTributario(models.IntegerChoices):
        PRESUMIDO = 1, "Lucro Presumido"
        REAL = 2, "Lucro Real"
        SN = 3, "Simples Nacional"
        OUTRO = 0, "Outro / Não informado"


    regime_tributario = models.IntegerField(
        choices=RegimeTributario.choices,
        default=RegimeTributario.OUTRO,
        blank=False,
    )

    class Atividade(models.IntegerChoices):
        OUTRO = 0, "Outro / Não informado"
        ATACADISTA = 1, "Atacadista"
        DISTRIBUIDOR = 2, "Distribuidor"
        FABRICA = 3, "Indústria / Fábrica"
        VAREJISTA = 4, "Varejista"

    atividade_origem = models.PositiveSmallIntegerField(choices=Atividade.choices, default=Atividade.OUTRO)
    atividade_destino = models.PositiveSmallIntegerField(choices=Atividade.choices, default=Atividade.OUTRO)

    cep = models.CharField(max_length=8, blank=True, default="")
    endereco = models.CharField(max_length=250, blank=True, default="")
    numero = models.CharField(max_length=20, blank=True, default="")
    bairro = models.CharField(max_length=120, blank=True, default="")
    municipio = models.CharField(max_length=120, blank=True, default="")
    uf = models.CharField(max_length=2, blank=True, default="")
    data_abertura = models.DateField(null=True, blank=True)

    cnae_principal = models.TextField(blank=True, default="")
    cnaes_secundarios = models.TextField(blank=True, default="")

    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    
    itens_substituto_tributario = models.TextField(
    blank=True,
    null=True,
    verbose_name="Itens de Substituição Tributária"
)

    class Meta:
        unique_together = ("conta", "cnpj")

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"
    
class UploadLote(models.Model):
    class Tipo(models.TextChoices):
        XML = "XML", "XML/ZIP"
        PLANILHA = "PLANILHA", "Planilha"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        PROCESSANDO = "PROCESSANDO", "Processando"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        ERRO = "ERRO", "Erro"

    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="uploads_lotes")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploads_lotes")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDENTE)
    observacao = models.CharField(max_length=255, blank=True, default="")
    total = models.PositiveIntegerField(default=0)
    processados = models.PositiveIntegerField(default=0)
    arquivo_atual = models.CharField(max_length=255, blank=True, default="")
    atualizado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    @property
    def percentual(self) -> float:
        if self.total > 0:
            return round(self.processados / self.total * 100, 1)
        return 0.0

    def __str__(self):
        return f"Lote {self.id} - {self.empresa_id} - {self.tipo} - {self.status}"

class UploadArquivo(models.Model):
    lote = models.ForeignKey(UploadLote, on_delete=models.CASCADE, related_name="arquivos")
    arquivo = models.FileField(upload_to="uploads/%Y/%m/")
    nome_original = models.CharField(max_length=255)
    extensao = models.CharField(max_length=10, blank=True, default="")
    tamanho = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome_original
    
class ProdutoNcm(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="produtos_ncm")
    produto = models.CharField(max_length=255)
    ncm = models.CharField(max_length=8, blank=True, default="")

    # rastreabilidade
    upload_lote = models.ForeignKey("core.UploadLote", on_delete=models.SET_NULL, null=True, blank=True)
    origem = models.CharField(max_length=20, default="IMPORT", blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["empresa", "produto", "ncm"], name="uniq_produto_ncm_por_empresa")
        ]

    def __str__(self):
        return f"{self.produto} ({self.ncm})"

class AnaliseNcmCache(models.Model):
    class Status(models.TextChoices):
        OK = "OK", "OK"
        ERRO = "ERRO", "Erro"

    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="analises_ncm_cache")

    # chave de consulta
    ncm = models.CharField(max_length=8)
    uf_origem = models.CharField(max_length=2, default="DF")
    uf_destino = models.CharField(max_length=2, default="GO")  # p/ ST interestadual
    regime_tributario = models.CharField(max_length=15, choices=Empresa.RegimeTributario.choices, default=Empresa.RegimeTributario.OUTRO)

    atividade_origem = models.PositiveSmallIntegerField(default=1)
    atividade_destino = models.PositiveSmallIntegerField(default=1)

    # metadados
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OK)
    erro_msg = models.TextField(blank=True, default="")
    consultado_em = models.DateTimeField(default=timezone.now)

    # resultado (melhor: JSONField para evoluir sem migração)
    resultado = models.JSONField(default=dict, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "empresa",
                    "ncm",
                    "uf_origem",
                    "uf_destino",
                    "regime_tributario",
                    "atividade_origem",
                    "atividade_destino",
                ],
                name="uniq_cache_analise_ncm_contexto",
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "ncm"], name="idx_cache_empresa_ncm"),
        ]

    def __str__(self):
        return f"{self.empresa_id} - {self.ncm} ({self.regime_tributario})"


class AnaliseNcmCacheCompartilhado(models.Model):
    """Cache compartilhado entre empresas com o mesmo contexto fiscal (NCM/UF/regime/atividades).

    O resultado do legisweb não depende de qual empresa pergunta, só do contexto — esta tabela
    evita reconsultar a API quando duas empresas diferentes têm exatamente as mesmas características.
    Independente do AnaliseNcmCache (que continua por empresa, usado para relatórios/auditoria).
    """
    class Status(models.TextChoices):
        OK = "OK", "OK"
        ERRO = "ERRO", "Erro"

    ncm = models.CharField(max_length=8)
    uf_origem = models.CharField(max_length=2, default="DF")
    uf_destino = models.CharField(max_length=2, default="GO")
    regime_tributario = models.CharField(max_length=15, choices=Empresa.RegimeTributario.choices, default=Empresa.RegimeTributario.OUTRO)

    atividade_origem = models.PositiveSmallIntegerField(default=1)
    atividade_destino = models.PositiveSmallIntegerField(default=1)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OK)
    erro_msg = models.TextField(blank=True, default="")
    resultado = models.JSONField(default=dict, blank=True)
    consultado_em = models.DateTimeField(default=timezone.now)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "ncm",
                    "uf_origem",
                    "uf_destino",
                    "regime_tributario",
                    "atividade_origem",
                    "atividade_destino",
                ],
                name="uniq_cache_ncm_compartilhado_contexto",
            ),
        ]

    def __str__(self):
        return f"{self.ncm} ({self.regime_tributario}) - {self.uf_origem}->{self.uf_destino}"


class AnaliseItem(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="analises_itens")
    upload_lote = models.ForeignKey(
    "core.UploadLote",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="analises_itens",
)

    # origem (se veio da planilha/xml)
    produto_ncm = models.ForeignKey("core.ProdutoNcm", on_delete=models.SET_NULL, null=True, blank=True)

    produto = models.CharField(max_length=255)
    ncm = models.CharField(max_length=8, blank=True, default="")

    # vínculo com cache
    cache = models.ForeignKey("core.AnaliseNcmCache", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens")

    # snapshot opcional para congelar a visualização (recomendado)
    resultado_snapshot = models.JSONField(default=dict, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    
    planilha_linha = models.ForeignKey(
        "core.PlanilhaLinhaOriginal",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="analises"
    )

    class Meta:
        indexes = [
            models.Index(fields=["empresa", "upload_lote"], name="idx_analise_empresa_lote"),
            models.Index(fields=["empresa", "ncm"], name="idx_analise_empresa_ncm"),
        ]

    def __str__(self):
        return f"{self.produto} ({self.ncm})"

class PlanilhaLinhaOriginal(models.Model):
    upload_lote = models.ForeignKey("core.UploadLote", on_delete=models.CASCADE, related_name="planilha_linhas")
    linha_idx = models.PositiveIntegerField()  # ordem original da planilha (0,1,2...)

    dados = models.JSONField(default=dict)  # { "Produto": "...", "NCM": "...", "CST": "...", ... }

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["upload_lote", "linha_idx"], name="uniq_planilha_lote_linha_idx")
        ]
        indexes = [
            models.Index(fields=["upload_lote", "linha_idx"], name="idx_planilha_lote_linha"),
        ]

class NotaFiscal(models.Model):
    class Tipo(models.TextChoices):
        NFE = "NFE", "NF-e"
        NFCE = "NFCE", "NFC-e"

    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="notas")
    upload_lote = models.ForeignKey("core.UploadLote", on_delete=models.SET_NULL, null=True, blank=True, related_name="notas")

    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.NFE)

    chave = models.CharField(max_length=44)
    numero = models.CharField(max_length=20, blank=True, default="")
    serie = models.CharField(max_length=10, blank=True, default="")
    modelo = models.CharField(max_length=5, blank=True, default="55")

    emissao_em = models.DateTimeField(null=True, blank=True)

    cnpj_emitente = models.CharField(max_length=14, blank=True, default="")
    cnpj_destinatario = models.CharField(max_length=14, blank=True, default="")

    valor_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_produtos = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    raw_resumo = models.JSONField(default=dict, blank=True)

    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["empresa", "chave"], name="uniq_nota_empresa_chave"),
        ]
        indexes = [
            models.Index(fields=["empresa", "chave"], name="idx_nota_empresa_chave"),
            models.Index(fields=["empresa", "emissao_em"], name="idx_nota_empresa_emissao"),
        ]

    def __str__(self):
        return f"{self.empresa_id} - {self.chave}"

class ItemNotaFiscal(models.Model):
    nota = models.ForeignKey("core.NotaFiscal", on_delete=models.CASCADE, related_name="itens")
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="itens_notas")
    upload_lote = models.ForeignKey("core.UploadLote", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_notas")

    n_item = models.PositiveIntegerField(default=0)

    produto = models.CharField(max_length=255, blank=True, default="")
    ncm = models.CharField(max_length=8, blank=True, default="")
    cfop = models.CharField(max_length=4, blank=True, default="")
    cest = models.CharField(max_length=7, blank=True, default="")

    qtd = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    v_un = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    v_prod = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # ICMS
    icms_cst = models.CharField(max_length=3, blank=True, default="")
    icms_csosn = models.CharField(max_length=4, blank=True, default="")
    icms_base = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    icms_aliq = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    icms_valor = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    icmsst_base = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    icmsst_aliq = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    icmsst_valor = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # PIS
    pis_cst = models.CharField(max_length=2, blank=True, default="")
    pis_base = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    pis_aliq = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    pis_valor = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # COFINS
    cofins_cst = models.CharField(max_length=2, blank=True, default="")
    cofins_base = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cofins_aliq = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    cofins_valor = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    raw_imposto = models.JSONField(default=dict, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    
    analise_item = models.ForeignKey(
        "core.AnaliseItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itens_nota"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["nota", "n_item"], name="uniq_item_por_nota"),
        ]
        indexes = [
            models.Index(fields=["empresa", "ncm"], name="idx_item_empresa_ncm"),
            models.Index(fields=["empresa", "cfop"], name="idx_item_empresa_cfop"),
        ]

    def __str__(self):
        return f"{self.nota_id}#{self.n_item} {self.produto}"
    
class FilaAnalise(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        ANALISANDO = "ANALISANDO", "Analisando"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        ERRO = "ERRO", "Erro"
        CANCELADO = "CANCELADO", "Cancelado"

    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="filas_analise")
    upload_lote = models.ForeignKey("core.UploadLote", on_delete=models.SET_NULL, null=True, blank=True, related_name="filas_analise")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDENTE)
    total = models.PositiveIntegerField(default=0)
    processados = models.PositiveIntegerField(default=0)
    produto_atual = models.CharField(max_length=255, blank=True, default="")
    erro_msg = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["empresa", "status"], name="idx_fila_empresa_status"),
        ]

    @property
    def percentual(self) -> float:
        if self.total > 0:
            return round(self.processados / self.total * 100, 1)
        return 0.0

    def __str__(self):
        return f"FilaAnalise #{self.id} - {self.empresa_id} - {self.status}"


class DivergenciaItem(models.Model):
    SEVERIDADE = (
        ("critica", "Crítica"),
        ("alta", "Alta"),
        ("media", "Média"),
        ("baixa", "Baixa"),
    )

    item = models.ForeignKey("ItemNotaFiscal", on_delete=models.CASCADE, related_name="divergencias")
    tipo = models.CharField(max_length=60)  # ex: "ICMS_CST", "PIS_CST", "COFINS_CST", "CFOP"
    esperado = models.CharField(max_length=255, blank=True, default="")
    encontrado = models.CharField(max_length=255, blank=True, default="")
    severidade = models.CharField(max_length=10, choices=SEVERIDADE, default="media")
    detalhe = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tipo"]),
            models.Index(fields=["severidade"]),
        ]
        