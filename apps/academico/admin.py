from django.contrib import admin

from .models import (
    Aula,
    Avaliacao,
    Curso,
    Disciplina,
    Evento,
    Frequencia,
    Justificativa,
    Matricula,
    Nota,
    Oferta,
    Turma,
)

# autocomplete_fields troca as listas suspensas por uma busca. Sem isso, os formulários de
# nota e frequência teriam de carregar milhares de opções vindas do Supabase.
# list_select_related busca os dados relacionados de uma vez, evitando uma consulta por linha.


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ("nome", "total_creditos")
    search_fields = ("nome",)


@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "curso", "creditos", "carga_horaria")
    list_filter = ("curso",)
    list_select_related = ("curso",)
    search_fields = ("codigo", "nome")


class OfertaInline(admin.TabularInline):
    """Permite definir as disciplinas e os professores na própria tela da turma."""

    model = Oferta
    extra = 0
    autocomplete_fields = ("disciplina", "professor")


@admin.register(Turma)
class TurmaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "semestre", "periodo", "curso")
    list_filter = ("semestre", "curso")
    list_select_related = ("curso",)
    search_fields = ("codigo", "semestre")
    inlines = (OfertaInline,)


@admin.register(Oferta)
class OfertaAdmin(admin.ModelAdmin):
    list_display = ("disciplina", "turma", "professor")
    list_filter = ("turma__semestre", "turma")
    list_select_related = ("disciplina", "turma", "professor")
    search_fields = (
        "disciplina__nome",
        "disciplina__codigo",
        "turma__codigo",
        "professor__first_name",
        "professor__last_name",
    )
    autocomplete_fields = ("turma", "disciplina", "professor")


@admin.register(Matricula)
class MatriculaAdmin(admin.ModelAdmin):
    list_display = ("aluno", "turma", "situacao", "creditos_concluidos", "coeficiente_rendimento")
    list_filter = ("situacao", "turma")
    list_select_related = ("aluno", "turma")
    search_fields = ("aluno__matricula", "aluno__first_name", "aluno__last_name", "turma__codigo")
    autocomplete_fields = ("aluno", "turma")


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "oferta", "tipo", "data_hora", "local")
    list_filter = ("tipo", "oferta__turma")
    list_select_related = ("oferta__disciplina", "oferta__turma")
    search_fields = ("nome", "oferta__disciplina__nome", "oferta__turma__codigo")
    autocomplete_fields = ("oferta",)
    date_hierarchy = "data_hora"


@admin.register(Nota)
class NotaAdmin(admin.ModelAdmin):
    list_display = ("matricula", "avaliacao", "valor", "atualizada_em")
    list_filter = ("avaliacao__oferta__turma", "avaliacao__oferta__disciplina")
    list_select_related = (
        "matricula__aluno",
        "matricula__turma",
        "avaliacao__oferta__disciplina",
        "avaliacao__oferta__turma",
    )
    search_fields = (
        "matricula__aluno__matricula",
        "matricula__aluno__first_name",
        "matricula__aluno__last_name",
    )
    autocomplete_fields = ("avaliacao", "matricula")


@admin.register(Aula)
class AulaAdmin(admin.ModelAdmin):
    list_display = ("data", "oferta", "horas_aula", "conteudo")
    list_filter = ("oferta__turma", "oferta__disciplina")
    list_select_related = ("oferta__disciplina", "oferta__turma")
    search_fields = ("oferta__disciplina__nome", "oferta__turma__codigo", "conteudo")
    autocomplete_fields = ("oferta",)
    date_hierarchy = "data"


@admin.register(Frequencia)
class FrequenciaAdmin(admin.ModelAdmin):
    list_display = ("matricula", "aula", "presente", "metodo", "registrada_em")
    list_filter = ("presente", "metodo", "aula__oferta__turma", "aula__oferta__disciplina")
    list_select_related = (
        "matricula__aluno",
        "matricula__turma",
        "aula__oferta__disciplina",
        "aula__oferta__turma",
    )
    search_fields = (
        "matricula__aluno__matricula",
        "matricula__aluno__first_name",
        "matricula__aluno__last_name",
    )
    autocomplete_fields = ("aula", "matricula")
    readonly_fields = ("registrada_em",)


@admin.register(Justificativa)
class JustificativaAdmin(admin.ModelAdmin):
    list_display = ("frequencia", "status", "avaliada_por", "criada_em", "avaliada_em")
    list_filter = ("status",)
    list_select_related = (
        "frequencia__matricula__aluno",
        "frequencia__matricula__turma",
        "frequencia__aula",
        "avaliada_por",
    )
    search_fields = (
        "frequencia__matricula__aluno__matricula",
        "frequencia__matricula__aluno__first_name",
        "frequencia__matricula__aluno__last_name",
    )
    autocomplete_fields = ("frequencia", "avaliada_por")
    readonly_fields = ("criada_em",)


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "inicio", "local", "oferta")
    list_filter = ("tipo",)
    list_select_related = ("oferta__disciplina", "oferta__turma")
    search_fields = ("titulo", "local")
    autocomplete_fields = ("oferta",)
    date_hierarchy = "inicio"
