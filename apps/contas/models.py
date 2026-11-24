from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

from .foto import VALIDADORES_FOTO, caminho_da_foto


class UsuarioManager(BaseUserManager):
    """Cria usuários usando a matrícula no lugar do nome de usuário padrão do Django."""

    use_in_migrations = True

    def _criar(self, matricula, password, **campos):
        if not matricula:
            raise ValueError("A matrícula é obrigatória.")
        campos["email"] = self.normalize_email(campos.get("email", ""))
        usuario = self.model(matricula=matricula, **campos)
        # set_password guarda apenas o hash; a senha em texto nunca vai para o banco.
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, matricula, password=None, **campos):
        campos.setdefault("is_staff", False)
        campos.setdefault("is_superuser", False)
        return self._criar(matricula, password, **campos)

    def create_superuser(self, matricula, password=None, **campos):
        # Superusuário sempre tem o perfil ADMIN e acesso ao Django Admin.
        campos["perfil"] = Usuario.Perfil.ADMIN
        campos["is_staff"] = True
        campos["is_superuser"] = True
        return self._criar(matricula, password, **campos)


class Usuario(AbstractUser):
    """Usuário do sistema. O login é feito por matrícula e senha."""

    class Perfil(models.TextChoices):
        ALUNO = "ALUNO", "Aluno"
        PROFESSOR = "PROFESSOR", "Professor"
        COORDENADOR = "COORDENADOR", "Coordenador"
        # Cuida só dos acessos (contas, senhas, desbloqueios). Não vê dados acadêmicos.
        SECRETARIA = "SECRETARIA", "Secretaria"
        ADMIN = "ADMIN", "Administrador"

    # Remove o campo "username" herdado de AbstractUser: quem identifica é a matrícula.
    username = None
    matricula = models.CharField("matrícula", max_length=20, unique=True)
    perfil = models.CharField(
        "perfil", max_length=11, choices=Perfil.choices, default=Perfil.ALUNO
    )
    # Informado no cadastro (ex.: "Prof." ou "Profa."), em vez de ser deduzido pelo nome.
    tratamento = models.CharField("tratamento", max_length=10, blank=True)
    # Foto do avatar, enviada pela própria pessoa (regras em apps/contas/foto.py).
    # O conteúdo fica no banco (ArquivoAnexo). O db_default="" deixa o banco preencher o campo
    # sozinho, para quem ainda roda a versão anterior do código conseguir criar contas.
    foto = models.FileField(
        "foto de perfil",
        upload_to=caminho_da_foto,
        blank=True,
        default="",
        db_default="",
        validators=VALIDADORES_FOTO,
    )
    # Ligado quando a Secretaria gera uma senha provisória: no próximo login, a pessoa só
    # consegue abrir a tela de troca de senha (apps/contas/middleware.py).
    precisa_trocar_senha = models.BooleanField(
        "precisa trocar a senha", default=False, db_default=False
    )
    # Momento do último pedido de link de "Esqueci minha senha". Entra no código do link
    # (apps/contas/tokens.py): pedir um link novo faz o anterior parar de funcionar.
    ultimo_pedido_reset = models.DateTimeField(
        "último pedido de redefinição", null=True, blank=True
    )

    # Campo usado na tela de login.
    USERNAME_FIELD = "matricula"
    # Pedido no comando createsuperuser; o e-mail é usado para redefinir a senha.
    REQUIRED_FIELDS = ["email"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["matricula"]

    def __str__(self):
        nome = self.get_full_name()
        return f"{self.matricula} - {nome}" if nome else self.matricula

    def save(self, *args, **kwargs):
        """Salva o usuário. Se a senha mudou, o token da API deixa de valer.

        O set_password() do Django guarda a senha nova em self._password até o save().
        Trocar a senha já encerra as sessões do portal; sem isto, quem tivesse copiado o
        token antigo continuaria entrando pela API. Vale para a senha provisória da
        Secretaria, o "Esqueci minha senha" e o Django Admin.
        """
        senha_mudou = self._password is not None
        super().save(*args, **kwargs)
        if senha_mudou:
            # Importado aqui para o app de contas não depender do DRF ao carregar.
            from rest_framework.authtoken.models import Token

            Token.objects.filter(user=self).delete()
            # Senha nova (pela Secretaria ou por "Esqueci minha senha") desbloqueia o login.
            BloqueioDeLogin.objects.filter(matricula=self.matricula).delete()

    @property
    def nome_com_tratamento(self):
        """Nome usado nas telas, como "Prof. Ricardo Almeida"."""
        return f"{self.tratamento} {self.get_full_name()}".strip()

    @property
    def iniciais(self):
        """Letras do avatar: primeiro e último nome, ou o começo da matrícula."""
        partes = self.get_full_name().split()
        if not partes:
            return self.matricula[:2].upper()
        if len(partes) == 1:
            return partes[0][0].upper()
        return (partes[0][0] + partes[-1][0]).upper()


class BloqueioDeLogin(models.Model):
    """Erros de senha seguidos de uma matrícula digitada no login.

    Conta pela matrícula digitada, exista ela ou não: assim o bloqueio e a mensagem são
    iguais para todas, e ninguém descobre pelo login quais matrículas existem.
    As regras (5 erros, 15 minutos) ficam em apps/contas/bloqueio.py.
    """

    matricula = models.CharField("matrícula digitada", max_length=150, unique=True)
    erros = models.PositiveSmallIntegerField("erros seguidos", default=0)
    ultimo_erro_em = models.DateTimeField("último erro em", null=True, blank=True)
    bloqueado_ate = models.DateTimeField("bloqueado até", null=True, blank=True)

    class Meta:
        verbose_name = "bloqueio de login"
        verbose_name_plural = "bloqueios de login"
        ordering = ["-ultimo_erro_em"]

    def __str__(self):
        return self.matricula


class RegistroDeAuditoria(models.Model):
    """Histórico das ações sensíveis sobre as contas: quem fez, em qual conta, o quê, quando e de onde.

    Nunca guarda senhas nem códigos de link. Os registros não são editados nem apagados pelo
    portal; o Django Admin só mostra. Exemplos de texto em "detalhe": o e-mail antigo e o
    novo (mascarados), ou o motivo de uma recusa.
    """

    class Acao(models.TextChoices):
        CONTA_CRIADA = "CONTA_CRIADA", "Conta criada"
        DADOS_ALTERADOS = "DADOS_ALTERADOS", "Dados de acesso alterados"
        EMAIL_ALTERADO = "EMAIL_ALTERADO", "E-mail alterado"
        LINK_ENVIADO = "LINK_ENVIADO", "Link de redefinição enviado"
        SENHA_PROVISORIA = "SENHA_PROVISORIA", "Senha provisória gerada"
        SENHA_REDEFINIDA = "SENHA_REDEFINIDA", "Senha redefinida pelo link"
        SENHA_ALTERADA = "SENHA_ALTERADA", "Senha alterada pela própria pessoa"
        DESBLOQUEIO = "DESBLOQUEIO", "Login desbloqueado"
        DESATIVACAO = "DESATIVACAO", "Conta desativada"
        REATIVACAO = "REATIVACAO", "Conta reativada"

    # SET_NULL no autor: o registro continua existindo mesmo se a conta de quem fez sumir.
    # Vazio também quando quem fez não estava logado (ex.: pedido de link pela tela pública).
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acoes_de_auditoria",
        verbose_name="quem fez",
    )
    conta = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="historico_de_acesso",
        verbose_name="conta",
    )
    acao = models.CharField("ação", max_length=20, choices=Acao.choices)
    detalhe = models.CharField("detalhe", max_length=200, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    criado_em = models.DateTimeField("data e hora", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-criado_em", "-pk"]
        indexes = [models.Index(fields=["conta", "-criado_em"])]

    def __str__(self):
        return f"{self.get_acao_display()} · {self.conta}"


class PedidoDeSenha(models.Model):
    """Um pedido de link de "Esqueci minha senha", usado para limitar os pedidos por hora.

    Fica no banco (e não na memória) pelo mesmo motivo do BloqueioDeLogin: na Vercel cada
    pedido pode cair em uma cópia diferente do sistema. Regras em apps/contas/redefinicao.py.
    "tipo" separa o pedido do link (ENVIO) da simples consulta da matrícula (CONSULTA).
    """

    class Tipo(models.TextChoices):
        CONSULTA = "CONSULTA", "Consulta da matrícula"
        ENVIO = "ENVIO", "Envio do link"

    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)
    matricula = models.CharField("matrícula digitada", max_length=150, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    criado_em = models.DateTimeField("pedido em", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "pedido de redefinição de senha"
        verbose_name_plural = "pedidos de redefinição de senha"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["tipo", "criado_em"])]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.matricula or self.ip}"
