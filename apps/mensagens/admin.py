from django.contrib import admin

from .models import Conversa, Mensagem


class MensagemInline(admin.TabularInline):
    model = Mensagem
    extra = 0
    autocomplete_fields = ("remetente",)


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = ("assunto", "aluno", "contato", "oferta", "criada_em")
    list_select_related = ("aluno", "contato", "oferta__disciplina", "oferta__turma")
    search_fields = ("assunto", "aluno__matricula", "contato__matricula")
    autocomplete_fields = ("aluno", "contato", "oferta")
    inlines = (MensagemInline,)
