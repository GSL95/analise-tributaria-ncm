# Migração consolidada das antigas 0007-0012 (não versionadas no repositório original).
# Gerada a partir do estado atual de core/models.py para manter a cadeia 0006 -> 0013 íntegra.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_analisencmcache_analiseitem_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='empresa',
            name='atividade_destino',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Outro / Não informado'), (1, 'Atacadista'), (2, 'Distribuidor'), (3, 'Indústria / Fábrica'), (4, 'Varejista')], default=0),
        ),
        migrations.AddField(
            model_name='empresa',
            name='atividade_origem',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Outro / Não informado'), (1, 'Atacadista'), (2, 'Distribuidor'), (3, 'Indústria / Fábrica'), (4, 'Varejista')], default=0),
        ),
        migrations.AddField(
            model_name='empresa',
            name='itens_substituto_tributario',
            field=models.TextField(blank=True, null=True, verbose_name='Itens de Substituição Tributária'),
        ),
        migrations.AddField(
            model_name='uploadlote',
            name='arquivo_atual',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='uploadlote',
            name='atualizado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='uploadlote',
            name='processados',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='uploadlote',
            name='total',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='analiseitem',
            name='upload_lote',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='analises_itens', to='core.uploadlote'),
        ),
        migrations.AlterField(
            model_name='analisencmcache',
            name='regime_tributario',
            field=models.CharField(choices=[(1, 'Lucro Presumido'), (2, 'Lucro Real'), (3, 'Simples Nacional'), (0, 'Outro / Não informado')], default=0, max_length=15),
        ),
        migrations.AlterField(
            model_name='empresa',
            name='regime_tributario',
            field=models.IntegerField(choices=[(1, 'Lucro Presumido'), (2, 'Lucro Real'), (3, 'Simples Nacional'), (0, 'Outro / Não informado')], default=0),
        ),
        migrations.CreateModel(
            name='NotaFiscal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('NFE', 'NF-e'), ('NFCE', 'NFC-e')], default='NFE', max_length=10)),
                ('chave', models.CharField(max_length=44)),
                ('numero', models.CharField(blank=True, default='', max_length=20)),
                ('serie', models.CharField(blank=True, default='', max_length=10)),
                ('modelo', models.CharField(blank=True, default='55', max_length=5)),
                ('emissao_em', models.DateTimeField(blank=True, null=True)),
                ('cnpj_emitente', models.CharField(blank=True, default='', max_length=14)),
                ('cnpj_destinatario', models.CharField(blank=True, default='', max_length=14)),
                ('valor_total', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('valor_produtos', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('raw_resumo', models.JSONField(blank=True, default=dict)),
                ('criada_em', models.DateTimeField(auto_now_add=True)),
                ('atualizada_em', models.DateTimeField(auto_now=True)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notas', to='core.empresa')),
                ('upload_lote', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notas', to='core.uploadlote')),
            ],
        ),
        migrations.CreateModel(
            name='ItemNotaFiscal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('n_item', models.PositiveIntegerField(default=0)),
                ('produto', models.CharField(blank=True, default='', max_length=255)),
                ('ncm', models.CharField(blank=True, default='', max_length=8)),
                ('cfop', models.CharField(blank=True, default='', max_length=4)),
                ('cest', models.CharField(blank=True, default='', max_length=7)),
                ('qtd', models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                ('v_un', models.DecimalField(decimal_places=6, default=0, max_digits=15)),
                ('v_prod', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('icms_cst', models.CharField(blank=True, default='', max_length=3)),
                ('icms_csosn', models.CharField(blank=True, default='', max_length=4)),
                ('icms_base', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('icms_aliq', models.DecimalField(decimal_places=4, default=0, max_digits=7)),
                ('icms_valor', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('icmsst_base', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('icmsst_aliq', models.DecimalField(decimal_places=4, default=0, max_digits=7)),
                ('icmsst_valor', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('pis_cst', models.CharField(blank=True, default='', max_length=2)),
                ('pis_base', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('pis_aliq', models.DecimalField(decimal_places=4, default=0, max_digits=7)),
                ('pis_valor', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('cofins_cst', models.CharField(blank=True, default='', max_length=2)),
                ('cofins_base', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('cofins_aliq', models.DecimalField(decimal_places=4, default=0, max_digits=7)),
                ('cofins_valor', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('raw_imposto', models.JSONField(blank=True, default=dict)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('analise_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='itens_nota', to='core.analiseitem')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens_notas', to='core.empresa')),
                ('upload_lote', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='itens_notas', to='core.uploadlote')),
                ('nota', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens', to='core.notafiscal')),
            ],
        ),
        migrations.CreateModel(
            name='PlanilhaLinhaOriginal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('linha_idx', models.PositiveIntegerField()),
                ('dados', models.JSONField(default=dict)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('upload_lote', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='planilha_linhas', to='core.uploadlote')),
            ],
        ),
        migrations.AddField(
            model_name='analiseitem',
            name='planilha_linha',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='analises', to='core.planilhalinhaoriginal'),
        ),
        migrations.CreateModel(
            name='FilaAnalise',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PENDENTE', 'Pendente'), ('ANALISANDO', 'Analisando'), ('CONCLUIDO', 'Concluído'), ('ERRO', 'Erro'), ('CANCELADO', 'Cancelado')], default='PENDENTE', max_length=15)),
                ('total', models.PositiveIntegerField(default=0)),
                ('processados', models.PositiveIntegerField(default=0)),
                ('produto_atual', models.CharField(blank=True, default='', max_length=255)),
                ('erro_msg', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('criado_por', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='filas_analise', to='core.empresa')),
                ('upload_lote', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='filas_analise', to='core.uploadlote')),
            ],
            options={
                'indexes': [models.Index(fields=['empresa', 'status'], name='idx_fila_empresa_status')],
            },
        ),
        migrations.CreateModel(
            name='DivergenciaItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(max_length=60)),
                ('esperado', models.CharField(blank=True, default='', max_length=255)),
                ('encontrado', models.CharField(blank=True, default='', max_length=255)),
                ('severidade', models.CharField(choices=[('critica', 'Crítica'), ('alta', 'Alta'), ('media', 'Média'), ('baixa', 'Baixa')], default='media', max_length=10)),
                ('detalhe', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='divergencias', to='core.itemnotafiscal')),
            ],
            options={
                'indexes': [models.Index(fields=['tipo'], name='core_diverg_tipo_43db26_idx'), models.Index(fields=['severidade'], name='core_diverg_severid_a5a044_idx')],
            },
        ),
        migrations.AddIndex(
            model_name='notafiscal',
            index=models.Index(fields=['empresa', 'chave'], name='idx_nota_empresa_chave'),
        ),
        migrations.AddIndex(
            model_name='notafiscal',
            index=models.Index(fields=['empresa', 'emissao_em'], name='idx_nota_empresa_emissao'),
        ),
        migrations.AddConstraint(
            model_name='notafiscal',
            constraint=models.UniqueConstraint(fields=('empresa', 'chave'), name='uniq_nota_empresa_chave'),
        ),
        migrations.AddIndex(
            model_name='itemnotafiscal',
            index=models.Index(fields=['empresa', 'ncm'], name='idx_item_empresa_ncm'),
        ),
        migrations.AddIndex(
            model_name='itemnotafiscal',
            index=models.Index(fields=['empresa', 'cfop'], name='idx_item_empresa_cfop'),
        ),
        migrations.AddConstraint(
            model_name='itemnotafiscal',
            constraint=models.UniqueConstraint(fields=('nota', 'n_item'), name='uniq_item_por_nota'),
        ),
        migrations.AddIndex(
            model_name='planilhalinhaoriginal',
            index=models.Index(fields=['upload_lote', 'linha_idx'], name='idx_planilha_lote_linha'),
        ),
        migrations.AddConstraint(
            model_name='planilhalinhaoriginal',
            constraint=models.UniqueConstraint(fields=('upload_lote', 'linha_idx'), name='uniq_planilha_lote_linha_idx'),
        ),
    ]
