"""Configurações do projeto Instituto Socrático.

Valores sensíveis (senha do banco e SECRET_KEY) não ficam aqui: eles vêm do arquivo .env,
que está fora do Git. O modelo desse arquivo é o .env.example.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Pasta raiz do projeto (onde está o manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega as variáveis do .env para o ambiente do processo.
# override=True faz o .env valer mais que valores antigos guardados no terminal: o VS Code
# copia o .env ao abrir o terminal, e essa cópia não acompanha as alterações no arquivo.
load_dotenv(BASE_DIR / ".env", override=True)


def variavel_obrigatoria(nome):
    """Lê uma variável do .env e explica o que fazer quando ela está faltando."""
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise ImproperlyConfigured(
            f"A variável {nome} não está preenchida no arquivo .env (veja o .env.example)."
        )
    return valor


# Segurança
SECRET_KEY = variavel_obrigatoria("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False").strip().lower() == "true"
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()
]


# Apps instalados
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps do projeto
    "apps.contas",
    "apps.academico",
    "apps.aluno",
    "apps.professor",
    "apps.coordenacao",
    "apps.mensagens",
    "apps.financeiro",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.contas.context_processors.menu_lateral",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Banco de dados
if "test" in sys.argv:
    # Os testes rodam em um SQLite em memória: são rápidos e não tocam nos dados do Supabase.
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
    }
else:
    # O sistema usa o PostgreSQL do Supabase, pelo Session pooler (porta 5432).
    url_do_banco = variavel_obrigatoria("DATABASE_URL")
    DATABASES = {
        "default": dj_database_url.parse(
            url_do_banco,
            conn_max_age=60,  # reaproveita a conexão por 60 segundos
            conn_health_checks=True,  # confere se a conexão reaproveitada ainda funciona
            ssl_require=url_do_banco.startswith("postgres"),  # exige conexão criptografada
        )
    }


# Usuário customizado: o login é feito por matrícula (apps/contas/models.py).
AUTH_USER_MODEL = "contas.Usuario"

# Rotas de login e saída. "/" (contas:inicio) manda cada perfil para a sua área.
LOGIN_URL = "contas:entrar"
LOGIN_REDIRECT_URL = "contas:inicio"
LOGOUT_REDIRECT_URL = "contas:entrar"

# Prazo do link de "Esqueci minha senha": 1 hora, em segundos.
PASSWORD_RESET_TIMEOUT = 60 * 60

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Idioma e fuso horário
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# Arquivos estáticos (CSS, JavaScript e imagens)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Anexos enviados pelos usuários. Esta pasta fica fora do Git e não tem rota pública em urls.py:
# atestados contêm dados pessoais e só serão entregues por uma view que confere a permissão.
MEDIA_ROOT = BASE_DIR / "media"

# E-mail. Em desenvolvimento, o backend de console mostra a mensagem no terminal do runserver.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "Instituto Socrático <nao-responda@institutosocratico.example>"
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
