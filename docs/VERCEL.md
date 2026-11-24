# Publicação na Vercel

Como o Instituto Socrático é publicado na internet e por que cada peça está do jeito que está.

## Como a Vercel roda o Django

A Vercel reconhece o projeto Django sozinha pelo `manage.py`. Ela lê o `WSGI_APPLICATION`
do `config/settings.py` (`config.wsgi.application`) e transforma o sistema inteiro em **uma
Vercel Function**: a cada pedido, a função acorda, o Django responde e o processo pode ser
desligado depois. Não existe um servidor ligado o tempo todo, e isso explica as escolhas abaixo.

| Peça | No computador | Na Vercel |
|---|---|---|
| Arquivos estáticos (CSS, JS, imagens, Admin, Swagger) | `runserver` entrega `static/` | O build roda o `collectstatic` sozinho (porque o `STATIC_ROOT` existe) e o CDN da Vercel entrega os arquivos. Sem WhiteNoise e sem biblioteca nova |
| Anexos e fotos de perfil | No banco (`ArquivoAnexo`) | Igual: o disco da Vercel é apagado, mas o banco não |
| Banco | Supabase, Session pooler (porta 5432) | Supabase, **Transaction pooler (porta 6543)**. O settings reconhece a porta e usa `CONN_MAX_AGE=0` e `DISABLE_SERVER_SIDE_CURSORS=True` |
| Celery | Worker + beat + Redis (ou `CELERY_SEM_REDIS=True`) | `CELERY_SEM_REDIS=True`: os avisos rodam na hora, dentro do pedido |
| Rotina das 6h | `celery beat` | **Cron da Vercel** (`vercel.json`) chama `GET /tarefas/rotina-diaria/` às 9h UTC (6h de Brasília) |
| Modelo de evasão | `ml/modelo_evasao.joblib` | O mesmo arquivo, que agora vai para o Git (cerca de 1,3 MB) |

### A rota do Cron

`apps/alertas/cron.py`. A Vercel manda o cabeçalho `Authorization: Bearer <CRON_SECRET>`. Com
o segredo certo, a rota roda `tasks.rotina_diaria()` (recalcula o risco e gera os alertas) e
responde um JSON com o resumo. Sem o segredo, ou com a variável `CRON_SECRET` vazia, responde
404. No plano gratuito (Hobby) o Cron roda uma vez por dia e pode atrasar até uma hora.

### Por que versionar o modelo

Treinar no build exigiria rodar código no build e confiar que o arquivo gerado entra no pacote.
Com o arquivo no Git, a Vercel publica exatamente o modelo testado. O treino é determinístico
(semente 42), então qualquer pessoa gera o mesmo arquivo. **Treinou de novo? Faça commit do
`ml/modelo_evasao.joblib` novo.** O `requirements.txt` fixa o `scikit-learn==1.9.1`, a mesma
versão no computador e na Vercel, e o arquivo só abre na mesma versão.

## Arquivos de configuração

- `vercel.json`: o Cron e o tempo máximo da função (`maxDuration` de 60 s, para a rotina diária
  e os relatórios maiores).
- `.python-version`: Python 3.12 na Vercel.
- `requirements.txt`: as dependências que a Vercel instala.
- `.vercelignore`: o que não sobe quando a publicação é feita pela CLI (`.venv`, `node_modules`, `.env`...).

## Passo a passo (uma vez)

1. **Importar o projeto:** em vercel.com, *Add New… > Project*, escolher o repositório
   `colegio-socratico` no GitHub. *Framework Preset*: **Django** (detectado sozinho). Não
   preencher *Build Command* nem *Output Directory*.
2. **Variáveis de ambiente** (*Settings > Environment Variables*, marcar Production e Preview):

   | Variável | Valor |
   |---|---|
   | `SECRET_KEY` | uma chave nova, **diferente** da do `.env`: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `DEBUG` | `False` |
   | `USAR_HTTPS` | `True` |
   | `DATABASE_URL` | Painel do Supabase > *Connect* > **Transaction pooler** > URI (porta **6543**), com a senha e `?sslmode=require` no fim |
   | `CELERY_SEM_REDIS` | `True` |
   | `CRON_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `SITE_URL` | o endereço final, ex.: `https://colegio-socratico.vercel.app` (links dos e-mails; o antigo `ENDERECO_DO_SITE` ainda funciona) |
   | `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
   | `EMAIL_HOST`, `EMAIL_PORT` | servidor e porta do SMTP, ex.: `smtp.gmail.com` e `587` |
   | `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | usuário e senha do SMTP (no Gmail, uma "senha de app", nunca a senha da conta) |
   | `EMAIL_USE_TLS` | `True` (porta 587) |
   | `DEFAULT_FROM_EMAIL` | remetente, ex.: `Instituto Socrático <nao-responda@seu-dominio>` |
   | `ALLOWED_HOSTS` | opcional: o domínio próprio, se houver. O endereço da Vercel entra sozinho (`VERCEL_URL` e `VERCEL_PROJECT_PRODUCTION_URL`) |

3. **Deploy.** Cada push na `main` publica em produção. Cada push em outra branch gera um
   endereço de teste (Preview).
4. **Conferir:** abrir o endereço, entrar com uma conta da demonstração, abrir `/admin/` (o CSS
   do Admin precisa aparecer) e `/api/docs/`. Em *Settings > Cron Jobs*, o botão *Run* roda a
   rotina na hora.

## O que continua sendo feito no computador

- **Migrações:** a Vercel não roda `migrate`. Migração nova é aplicada do computador
  (`python manage.py migrate`, com o `.env` apontando para o Supabase) **antes** do push.
- **Dados de demonstração e treino do modelo:** `popular_demo` e `treinar_modelo`, também pelo
  computador.
- **CSS do Tailwind:** `npm run css` e commit do `static/css/app.css`. A Vercel não roda o Node.

## Limites que vale saber

- **E-mail:** sem um servidor SMTP nas variáveis (`EMAIL_BACKEND` e as `EMAIL_*`), os e-mails
  (link de nova senha, aviso de senha alterada, aviso de troca de e-mail e alertas "Em risco") só
  aparecem no log da função, em *Deployments > Logs*. Com o prazo de 10 minutos do link, o SMTP é
  necessário para o "Esqueci minha senha" funcionar de verdade. Na Vercel (`CELERY_SEM_REDIS=True`)
  o e-mail sai na hora, dentro do pedido, com limite de 10 segundos (`EMAIL_TIMEOUT`).
- **Conferência:** com `DEBUG=False` e sem SMTP, o `python manage.py check` mostra o aviso
  `contas.W001`, e a tela da conta na Secretaria avisa que o link não chega (sugerindo a senha
  provisória).
- **Limite de pedidos de link:** fica no banco (tabela `PedidoDeSenha`), e não na memória, porque
  cada pedido pode cair numa cópia diferente da função.
- **Tamanho do pacote:** o limite da função Python é de 500 MB. pandas, scikit-learn, scipy e
  matplotlib são os maiores, e o projeto fica abaixo do limite. Se uma biblioteca nova estourar,
  o build avisa.
- **Primeiro pedido mais lento:** quando a função está "fria", o Django e o pandas levam alguns
  segundos para carregar.
- **Redis/Upstash:** não é necessário na Vercel. Com `CELERY_SEM_REDIS=True`, nada usa fila.
