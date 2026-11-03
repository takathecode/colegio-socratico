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
