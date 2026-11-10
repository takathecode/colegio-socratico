from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


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
        ADMIN = "ADMIN", "Administrador"

    # Remove o campo "username" herdado de AbstractUser: quem identifica é a matrícula.
    username = None
    matricula = models.CharField("matrícula", max_length=20, unique=True)
    perfil = models.CharField(
        "perfil", max_length=11, choices=Perfil.choices, default=Perfil.ALUNO
    )
    # Informado no cadastro (ex.: "Prof." ou "Profa."), em vez de ser deduzido pelo nome.
    tratamento = models.CharField("tratamento", max_length=10, blank=True)

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
        coordenação, o "Esqueci minha senha" e o Django Admin.
        """
        senha_mudou = self._password is not None
        super().save(*args, **kwargs)
        if senha_mudou:
            # Importado aqui para o app de contas não depender do DRF ao carregar.
            from rest_framework.authtoken.models import Token

            Token.objects.filter(user=self).delete()
            # Senha nova (pela coordenação ou por "Esqueci minha senha") desbloqueia o login.
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
