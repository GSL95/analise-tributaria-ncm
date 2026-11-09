from django.db import migrations


def backfill_cache_compartilhado(apps, schema_editor):
    """Popula AnaliseNcmCacheCompartilhado a partir dos caches OK já existentes por empresa,
    para que empresas com o mesmo contexto fiscal já se beneficiem de consultas anteriores.
    Em caso de mais de uma empresa com o mesmo contexto, mantém o resultado mais recente."""
    AnaliseNcmCache = apps.get_model("core", "AnaliseNcmCache")
    AnaliseNcmCacheCompartilhado = apps.get_model("core", "AnaliseNcmCacheCompartilhado")

    mais_recentes = {}
    qs = (
        AnaliseNcmCache.objects.filter(status="OK")
        .exclude(resultado={})
        .values(
            "ncm",
            "uf_origem",
            "uf_destino",
            "regime_tributario",
            "atividade_origem",
            "atividade_destino",
            "resultado",
            "consultado_em",
        )
    )
    for row in qs.iterator():
        chave = (
            row["ncm"],
            row["uf_origem"],
            row["uf_destino"],
            row["regime_tributario"],
            row["atividade_origem"],
            row["atividade_destino"],
        )
        atual = mais_recentes.get(chave)
        if atual is None or row["consultado_em"] > atual["consultado_em"]:
            mais_recentes[chave] = row

    for chave, row in mais_recentes.items():
        ncm, uf_origem, uf_destino, regime_tributario, atividade_origem, atividade_destino = chave
        AnaliseNcmCacheCompartilhado.objects.update_or_create(
            ncm=ncm,
            uf_origem=uf_origem,
            uf_destino=uf_destino,
            regime_tributario=regime_tributario,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            defaults={
                "status": "OK",
                "erro_msg": "",
                "resultado": row["resultado"],
                "consultado_em": row["consultado_em"],
            },
        )


def reverter_backfill(apps, schema_editor):
    AnaliseNcmCacheCompartilhado = apps.get_model("core", "AnaliseNcmCacheCompartilhado")
    AnaliseNcmCacheCompartilhado.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_analisencmcachecompartilhado'),
    ]

    operations = [
        migrations.RunPython(backfill_cache_compartilhado, reverter_backfill),
    ]
