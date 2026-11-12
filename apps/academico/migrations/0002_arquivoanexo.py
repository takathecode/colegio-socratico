import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academico", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArquivoAnexo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=255, unique=True, verbose_name="nome")),
                ("conteudo", models.BinaryField(verbose_name="conteúdo")),
                ("tamanho", models.PositiveIntegerField(verbose_name="tamanho (bytes)")),
                ("criado_em", models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name="criado em")),
            ],
            options={
                "verbose_name": "arquivo anexo",
                "verbose_name_plural": "arquivos anexos",
            },
        ),
    ]
