"""Configurações do projeto Instituto Socrático.

Valores sensíveis (senha do banco e SECRET_KEY) não ficam aqui: eles vêm do arquivo .env,
que está fora do Git. O modelo desse arquivo é o .env.example.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
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

# HTTPS: ligar só no servidor publicado (Vercel). No computador o site abre em http://,
# e com isto ligado o navegador não guardaria o cookie do login.
USAR_HTTPS = os.getenv("USAR_HTTPS", "False").strip().lower() == "true"
if USAR_HTTPS:
    # Na Vercel o HTTPS termina no proxy, que avisa o Django por este cabeçalho. Sem ele, o
    # Django acharia que a conexão é http:// e recusaria os formulários (proteção CSRF).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True  # quem abrir em http:// é levado para https://
    SESSION_COOKIE_SECURE = True  # cookie do login só trafega por HTTPS
    CSRF_COOKIE_SECURE = True
    # HSTS: o navegador passa a usar só HTTPS neste endereço por 1 dia. Valor curto de
    # propósito, sem subdomínios e sem "preload", para um erro de configuração ser reversível.
    SECURE_HSTS_SECONDS = 60 * 60 * 24
    # O "check --deploy" sugere ligar os dois; ficam desligados pela escolha acima
    # (o domínio .vercel.app não é nosso, então não cabe pedir regras para os subdomínios).
    SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]


# Apps instalados
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Bibliotecas
    "django_filters",  # filtros dos relatórios e da API
    "rest_framework",  # API REST (apps/api)
    "rest_framework.authtoken",  # tabela dos tokens de acesso à API
    "drf_spectacular",  # documentação da API em /api/docs/
    # Apps do projeto
    "apps.contas",
    "apps.academico",
    "apps.aluno",
    "apps.professor",
    "apps.coordenacao",
    "apps.mensagens",
    "apps.financeiro",
    "apps.analytics",
    "apps.alertas",
    "apps.relatorios",
    "apps.api",
    "apps.videochamadas",
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
                "apps.alertas.context_processors.sino",
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

# Login padrão do Django com o bloqueio depois de 5 senhas erradas (apps/contas/bloqueio.py).
# Vale para a tela de login, o token da API e o Django Admin.
AUTHENTICATION_BACKENDS = ["apps.contas.backends.LoginComBloqueio"]

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

# Os anexos são gravados no banco (modelo academico.ArquivoAnexo), e não na pasta media/: o banco é
# o mesmo para todos os computadores, então o anexo enviado em uma máquina chega a quem abre a
# conversa em outra. A pasta media/ só é lida para anexos antigos (comando migrar_anexos).
STORAGES = {
    "default": {"BACKEND": "apps.academico.armazenamento.ArmazenamentoNoBanco"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# E-mail. Em desenvolvimento, o backend de console mostra a mensagem no terminal do runserver.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "Instituto Socrático <nao-responda@institutosocratico.example>"
)

# Modelo de evasão treinado pelo comando treinar_modelo. A pasta ml/ fica fora do Git.
MODELO_EVASAO = BASE_DIR / "ml" / "modelo_evasao.joblib"

# Endereço do sistema, usado para montar os links dos e-mails de alerta.
ENDERECO_DO_SITE = os.getenv("ENDERECO_DO_SITE", "http://127.0.0.1:8000").rstrip("/")

# Servidor do Jitsi Meet usado nas videochamadas (apps/videochamadas). O padrão é o serviço
# público e gratuito; uma escola com servidor próprio do Jitsi troca só esta linha no .env.
JITSI_SERVIDOR = os.getenv("JITSI_SERVIDOR", "https://meet.jit.si").strip().rstrip("/")


# Celery + Redis (config/celery.py e apps/alertas/tasks.py)
def endereco_do_redis():
    """Lê o REDIS_URL. O Upstash usa rediss:// (com S, criptografado), e o Celery exige que
    esse endereço diga se confere o certificado: sem o parâmetro, acrescentamos "required"."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        url += ("&" if "?" in url else "?") + "ssl_cert_reqs=required"
    return url


CELERY_BROKER_URL = endereco_do_redis()
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_IGNORE_RESULT = True  # as tarefas gravam o resultado no banco, não no Redis
# Sem Redis, a view não pode ficar travada esperando: desiste da fila em cerca de 2 segundos
# e apps/alertas/fila.py roda a tarefa na hora. socket_connect_timeout: 1 segundo basta para
# abrir a conexão com o Redis local ou com o Upstash. max_retries: 0 faz a tela não insistir
# na conexão. Sem esses dois limites, o Windows levava de 4 a 6 segundos para desistir.
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_connect_timeout": 1, "max_retries": 0}
CELERY_TASK_PUBLISH_RETRY = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# CELERY_SEM_REDIS=True no .env: as tarefas rodam na hora, dentro do próprio Django, sem fila.
# Serve para usar o sistema em um computador sem Redis. Os testes também rodam assim.
CELERY_TASK_ALWAYS_EAGER = (
    os.getenv("CELERY_SEM_REDIS", "False").strip().lower() == "true" or "test" in sys.argv
)

# Rotina diária: recalcula o risco de evasão e gera os alertas, todo dia às 6h.
CELERY_BEAT_SCHEDULE = {
    "rotina-diaria-de-alertas": {
        "task": "apps.alertas.tasks.rotina_diaria",
        "schedule": crontab(hour=6, minute=0),
    },
}


# API REST (Django REST Framework). Explicação em docs/API.md.
REST_FRAMEWORK = {
    # Login por token (outros sistemas) ou pela sessão do navegador (quem já entrou no portal).
    # O token vem primeiro para quem chega sem login receber 401 (e não 403), com o aviso
    # "WWW-Authenticate: Token" dizendo como se identificar.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Toda a API exige login, e só os perfis do portal entram (ADMIN usa o Django Admin).
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.api.permissoes.PerfilDoPortal",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.api.paginacao.Paginacao",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Notas e percentuais saem como número no JSON (6.75), e não como texto ("6.75").
    "COERCE_DECIMAL_TO_STRING": False,
    # Limite de pedidos de token, contra quem tenta adivinhar senhas.
    "DEFAULT_THROTTLE_RATES": {"token": "10/minute"},
}

# Documentação gerada pelo drf-spectacular (/api/schema/ e a tela /api/docs/).
SPECTACULAR_SETTINGS = {
    "TITLE": "API do Instituto Socrático",
    "DESCRIPTION": (
        "Consulta de alunos, turmas, desempenho, risco de evasão e relatórios, para a "
        "integração com outros sistemas da escola. A API só consulta (GET); as gravações "
        "ficam nas telas do portal.\n\n"
        "**Como entrar:** quem já fez login no portal usa a API direto pelo navegador. "
        "Outros sistemas pedem um token em `POST /api/token/` (matrícula e senha) e o "
        "enviam no cabeçalho `Authorization: Token <token>` (botão **Authorize**).\n\n"
        "**O que cada perfil vê:** aluno, os próprios dados; professor, as disciplinas que "
        "leciona; coordenação, a instituição inteira. Perfil sem acesso ao endpoint recebe "
        "403, e registro fora do que a pessoa pode ver responde 404."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,  # não lista o próprio /api/schema/ na documentação
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},  # guarda o token ao recarregar
    # A tela do Swagger vem do CDN. A versão fica fixa para ela não mudar sozinha
    # (o padrão é "latest", que acompanha cada lançamento novo).
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14",
    "SWAGGER_UI_FAVICON_HREF": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/favicon-32x32.png",
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
