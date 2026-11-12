# Instituto Socrático — Sistema de Gestão Acadêmica Inteligente

Projeto final do curso de Desenvolvimento de Sistemas (SENAI Morvan Figueiredo).

Sistema acadêmico em Django, com banco PostgreSQL no Supabase e uma área para cada perfil:

- **Aluno:** painel com gráfico de notas, boletim (com PDF), frequência, justificativa de faltas
  com anexo, calendário, mensagens e financeiro (simulado).
- **Professor:** turmas, lançamento de notas, chamada com simulação de biometria, avaliação de
  justificativas, gráfico de desempenho, relatórios da disciplina e videochamada com a coordenação.
- **Coordenação:** visão geral, alunos em risco de evasão (modelo de machine learning), cadastro
  de alunos, professores, turmas e disciplinas, criação de contas, relatórios em PDF e Excel e
  central de alertas e videochamada com os professores (Jitsi Meet).

Também tem alertas automáticos (Celery + Redis), notificações no sino e uma API REST documentada
em `/api/docs/`. Não existe tela de cadastro: as contas são criadas pela coordenação ou pelo
Django Admin.

---

## 1. O que instalar antes

| Programa | Para quê | Obrigatório? |
|---|---|---|
| [Python 3.12 ou mais novo](https://www.python.org/downloads/) | Rodar o sistema | Sim |
| [Git](https://git-scm.com/downloads) | Baixar o projeto | Sim |
| Conta no [Supabase](https://supabase.com/) | Banco de dados (PostgreSQL) | Sim |
| Conta no [Upstash](https://upstash.com/) ou Docker | Redis, a fila dos alertas automáticos | Não (veja o passo 7) |
| [Node.js](https://nodejs.org/) | Só para mudar o visual (Tailwind) | Não |

Na instalação do Python no Windows, marque a opção **"Add python.exe to PATH"**.

## 2. Baixar o projeto e criar o ambiente virtual

No PowerShell, dentro da pasta onde o projeto vai ficar:

```powershell
git clone <endereço do repositório>
cd projeto-escolar
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Se o PowerShell bloquear o `activate`, rode uma vez e tente de novo:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Toda vez que abrir um terminal novo, ative o ambiente de novo com `.venv\Scripts\activate`.
O começo da linha passa a mostrar `(.venv)`.

## 3. Configurar o `.env`

```powershell
Copy-Item .env.example .env
```

Abra o `.env` e preencha. Cada variável tem a explicação no próprio arquivo. As principais:

| Variável | O que colocar |
|---|---|
| `SECRET_KEY` | Uma chave aleatória. Gere com `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DEBUG` | `True` no computador de desenvolvimento |
| `DATABASE_URL` | A URL do Supabase (passo 4) |
| `REDIS_URL` e `CELERY_SEM_REDIS` | Veja o passo 7. Sem Redis, use `CELERY_SEM_REDIS=True` |
| `USAR_HTTPS` | `False` no computador. `True` só no servidor publicado |

O `.env` tem senhas e **nunca** vai para o Git (ele está no `.gitignore`).

## 4. Conectar ao banco (Supabase)

1. No painel do projeto no Supabase, clique em **Connect**.
2. Escolha **Session pooler** e copie a URI.
3. Cole no `DATABASE_URL` do `.env`, troque `[YOUR-PASSWORD]` pela senha do banco e mantenha
   `?sslmode=require` no final.

Se a senha tiver `@ : / ? #`, ela precisa estar codificada para URL (por exemplo, `@` vira `%40`).

As tabelas são criadas **somente** pelas migrações do Django. Não crie tabelas pelo painel do Supabase:

```powershell
python manage.py migrate
python manage.py createsuperuser    # conta de administrador: matrícula admin01, por exemplo
```

> **Rede do SENAI:** ela aceita a conexão na porta 5432 do Supabase, mas a conexão nunca se
> completa, e o Django fica parado sem mostrar erro. Nesse caso, use outra rede, como o roteador
> do celular.

## 5. Dados de demonstração e modelo de evasão

```powershell
python manage.py popular_demo      # 1 coordenador, 6 professores, 2 turmas e 40 alunos fictícios
python manage.py treinar_modelo    # treina o modelo de evasão e calcula o risco de cada aluno
```

- O `popular_demo` só roda com `DEBUG=True`. Rodar de novo apaga e recria apenas os dados de
  demonstração, com as datas ajustadas para o dia atual.
- O `treinar_modelo` grava o modelo em `ml/modelo_evasao.joblib`. O arquivo não vai para o Git,
  então cada computador treina o seu (leva poucos segundos). Sem ele, a tela "Alunos em risco"
  explica como treinar.

## 6. Rodar o sistema

```powershell
python manage.py runserver
```

Deixe esse terminal aberto: o site só funciona enquanto o `runserver` estiver rodando.

| Endereço | O que é |
|---|---|
| http://127.0.0.1:8000/ | Portal (login por matrícula e senha) |
| http://127.0.0.1:8000/admin/ | Django Admin |
| http://127.0.0.1:8000/api/docs/ | Documentação da API (Swagger) |

### Acessos de teste (criados pelo `popular_demo`)

A senha é igual à matrícula. Essas contas existem só para desenvolvimento e demonstração.

| Perfil | Matrícula | Observação |
|---|---|---|
| Administrador | `admin01` | Criada no passo 4 com `createsuperuser`; o `popular_demo` não recria |
| Coordenador | `coord01` | |
| Professor | `prof01` a `prof06` | Um por disciplina |
| Aluno | `aluno01` a `aluno40` | `aluno01` reproduz os dados do protótipo |

Alunos com dados de risco: `aluno05`, `aluno09`, `aluno14`, `aluno18`, `aluno23`, `aluno27`,
`aluno32` e `aluno38`.

Em "Esqueci minha senha", durante o desenvolvimento, o e-mail com o link aparece no terminal do
`runserver`. Depois de 5 senhas erradas seguidas, a matrícula fica bloqueada por 15 minutos.
Trocar a senha libera na hora.

## 7. Alertas automáticos (Celery + Redis), opcional

Os alertas (frequência baixa, média baixa, risco de evasão, justificativas paradas) são gerados
por uma rotina diária às 6h. Há duas formas de rodar:

**Sem Redis (mais simples):** no `.env`, `CELERY_SEM_REDIS=True`. As tarefas rodam na hora, dentro
do próprio `runserver`, e a rotina diária é disparada pelo botão "Rodar rotina agora" da Central de
alertas ou por:

```powershell
python manage.py gerar_alertas
```

**Com Redis (como em produção):**

1. Crie o Redis:
   - **Upstash (recomendado, é o que funciona nas máquinas do SENAI):** crie um banco gratuito em
     upstash.com e copie a URL `rediss://default:SENHA@HOST.upstash.io:6379` para o `REDIS_URL`.
   - **Docker:** `docker run -d -p 6379:6379 redis` e `REDIS_URL=redis://localhost:6379/0`.
2. No `.env`, `CELERY_SEM_REDIS=False`.
3. Abra mais dois terminais (com o `.venv` ativado), além do `runserver`:

```powershell
celery -A config worker --pool=solo -l info    # executa as tarefas (no Windows, --pool=solo é obrigatório)
celery -A config beat -l info                  # agenda a rotina das 6h
```

Se o Redis cair, o sistema não trava: depois de cerca de 2 segundos, a tarefa roda na hora.
Detalhes em [docs/ALERTAS.md](docs/ALERTAS.md).

## 8. Mudar o visual (Tailwind CSS), opcional

O CSS compilado (`static/css/app.css`) já vem no projeto, então o sistema roda sem o Node. Só
compile de novo depois de usar classes novas do Tailwind nos templates:

```powershell
npm install        # somente na primeira vez, em cada computador
npm run css        # compila uma vez
npm run css:dev    # ou deixe em um terminal separado, recompilando a cada alteração
```

## 9. Testes

```powershell
python manage.py check    # confere a configuração do projeto
python manage.py test     # roda todos os testes
```

Os testes usam um banco SQLite na memória: não precisam de internet nem do Redis e não tocam nos
dados do Supabase. Entre eles:

- **Login e bloqueio** (`apps/contas/test_login.py`): login por matrícula, "Manter conectado",
  redefinição de senha e bloqueio depois de 5 senhas erradas.
- **Varredura de permissões** (`apps/contas/test_permissoes.py`): percorre todas as rotas do
  sistema e confere que o visitante vai para o login e que cada perfil errado recebe 403. Uma tela
  nova sem `@perfil_requerido` faz o teste falhar.
- **Telas com dados de demonstração** (`apps/contas/test_telas_demo.py`): roda o `popular_demo`,
  treina o modelo e abre todas as telas de cada perfil, sem erro.
- **Módulo preditivo** (`apps/analytics/tests.py`): treino, cálculo do risco, motivos, e se o
  modelo encontra os alunos de risco da demonstração.

## 10. Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `A variável SECRET_KEY não está preenchida` | Falta o `.env` ou a variável (passo 3) |
| O `migrate` ou o `runserver` fica parado, sem erro | Rede bloqueando a porta 5432 (rede do SENAI). Troque de rede |
| `password authentication failed` | Senha errada no `DATABASE_URL`, ou com caractere especial sem codificar |
| "Alunos em risco" pede para treinar o modelo | Rode `python manage.py treinar_modelo` |
| Download de anexo antigo responde "não encontrado" | O anexo foi enviado antes de os anexos irem para o banco e ficou na pasta `media/` de outro computador. Nessa máquina, rode `python manage.py migrar_anexos` |
| O worker do Celery trava no Windows | Faltou `--pool=solo` |
| O navegador troca para `https://127.0.0.1` e a página não abre | `USAR_HTTPS=True` no `.env`: no computador, use `False` |
| Classe nova do Tailwind sem efeito | Rode `npm run css` |

## 11. Estrutura do projeto

```
config/            configurações (settings.py), rotas principais e Celery
apps/contas/       usuário customizado, login, bloqueio de senhas erradas e permissões por perfil
apps/academico/    cursos, turmas, disciplinas, matrículas, notas, frequência (DER em docs/DER.md)
apps/aluno/        área do aluno           → /aluno/
apps/professor/    área do professor       → /professor/
apps/coordenacao/  área da coordenação     → /coordenacao/
apps/mensagens/    caixa de mensagens      → /mensagens/
apps/videochamadas/ videochamadas (Jitsi Meet) entre coordenação e professores → /videochamadas/
apps/alertas/      alertas, sino de notificações e tarefas do Celery → /alertas/
apps/analytics/    gráficos (matplotlib) e módulo preditivo (scikit-learn)
apps/relatorios/   PDF (reportlab) e Excel (pandas) → /relatorios/
apps/financeiro/   mensalidades (simulado)
apps/api/          API REST → /api/ e /api/docs/
templates/         esqueleto, layout e componentes reutilizáveis
static/            CSS compilado, JavaScript e imagens
ml/                modelo treinado (gerado pelo treinar_modelo, fora do Git)
docs/              documentação para a apresentação
```

## 12. Documentação

| Documento | Assunto |
|---|---|
| [docs/DER.md](docs/DER.md) | Modelo de dados e decisões de modelagem |
| [docs/MODELO_EVASAO.md](docs/MODELO_EVASAO.md) | Como funciona o módulo preditivo de evasão |
| [docs/ALERTAS.md](docs/ALERTAS.md) | Alertas automáticos com Celery e Redis |
| [docs/RELATORIOS.md](docs/RELATORIOS.md) | Relatórios em PDF e Excel |
| [docs/API.md](docs/API.md) | API REST: token, endpoints e exemplos |
| [docs/SEGURANCA.md](docs/SEGURANCA.md) | Login, perfis, permissões e proteção dos dados |
| [docs/VIDEOCHAMADA.md](docs/VIDEOCHAMADA.md) | Videochamada entre coordenação e professores |

A publicação na internet (Vercel) é a próxima etapa do projeto e terá um guia próprio.
