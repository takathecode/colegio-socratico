"""Configurações do projeto Colégio Socrático.

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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
