from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm

from .models import BloqueioDeLogin, PedidoDeSenha, RegistroDeAuditoria, Usuario


class UsuarioCriacaoForm(AdminUserCreationForm):
    """Formulário de "adicionar usuário" do Admin, trocando username por matrícula."""

    class Meta:
        model = Usuario
        fields = ("matricula",)


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Adapta o Admin padrão de usuários, que espera um campo username."""

    add_form = UsuarioCriacaoForm

    list_display = ("matricula", "first_name", "last_name", "email", "perfil", "is_active")
    list_filter = ("perfil", "is_active", "is_staff", "precisa_trocar_senha")
    search_fields = ("matricula", "first_name", "last_name", "email")
    ordering = ("matricula",)

    # Tela de edição de um usuário existente.
    fieldsets = (
        (None, {"fields": ("matricula", "password")}),
        ("Dados pessoais", {"fields": ("tratamento", "first_name", "last_name", "email")}),
        ("Perfil no sistema", {"fields": ("perfil", "precisa_trocar_senha")}),
        (
            "Permissões",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
    )

    # Tela de criação de um usuário novo.
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "matricula",
                    "tratamento",
                    "first_name",
                    "last_name",
                    "email",
                    "perfil",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


class SomenteLeituraAdmin(admin.ModelAdmin):
    """Registros gravados só pelo sistema: o Admin mostra, mas não cria nem altera."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RegistroDeAuditoria)
class RegistroDeAuditoriaAdmin(SomenteLeituraAdmin):
    """Histórico das ações sensíveis nas contas. Nunca contém senhas nem códigos de link."""

    list_display = ("criado_em", "acao", "conta", "autor", "ip", "detalhe")
    list_filter = ("acao",)
    search_fields = ("conta__matricula", "conta__first_name", "autor__matricula", "ip")
    list_select_related = ("conta", "autor")
    date_hierarchy = "criado_em"

    def has_delete_permission(self, request, obj=None):
        return False  # a auditoria não se apaga


@admin.register(PedidoDeSenha)
class PedidoDeSenhaAdmin(SomenteLeituraAdmin):
    """Pedidos de "Esqueci minha senha", usados no limite por hora (apagados depois de 1 dia)."""

    list_display = ("criado_em", "tipo", "matricula", "ip")
    list_filter = ("tipo",)
    search_fields = ("matricula", "ip")


@admin.register(BloqueioDeLogin)
class BloqueioDeLoginAdmin(admin.ModelAdmin):
    """Matrículas com senhas erradas. Apagar o registro libera o login na hora."""

    list_display = ("matricula", "erros", "ultimo_erro_em", "bloqueado_ate")
    search_fields = ("matricula",)
    readonly_fields = ("matricula", "erros", "ultimo_erro_em", "bloqueado_ate")

    def has_add_permission(self, request):
        return False  # os registros são criados só pelo login
