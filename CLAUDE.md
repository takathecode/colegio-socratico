# Instituto Socrático — Sistema de Gestão Acadêmica Inteligente (TCC SENAI)

Projeto final do curso de Desenvolvimento de Sistemas (SENAI Morvan Figueiredo).
Sistema acadêmico em Django com banco PostgreSQL hospedado no **Supabase**, três áreas
separadas por perfil (aluno, professor, coordenador), dashboards, módulo preditivo de
evasão, alertas automáticos, relatórios PDF/Excel e API REST.

Responda e escreva comentários, mensagens de commit e textos de interface em **português do Brasil**.

## Referências
- **Protótipo Figma (fonte da verdade do visual):**
  https://www.figma.com/design/Vg4TMgHDW53cZ7HsbtZUOB/Col%C3%A9gio-Socr%C3%A1tico?node-id=0-1
  (file key `Vg4TMgHDW53cZ7HsbtZUOB`). Cópia em imagem: `docs/prototipo/prototipo.png`.
- **Projeto Supabase:** ref `rgfnazeqoepnefmjoljc`
  (https://supabase.com/dashboard/project/rgfnazeqoepnefmjoljc). Usar o MCP do Supabase só
  para consultar; o schema vem das migrações do Django.
- **Enunciado do professor:** `docs/TEMA_8.pdf`.

## Ambiente
- Sistema operacional dos desenvolvedores: **Windows** (use comandos PowerShell; caminhos com `\`).
- Python 3.12+, ambiente virtual em `.venv` (`.venv\Scripts\activate`).
- Banco: Supabase (PostgreSQL). Conexão pela variável `DATABASE_URL` no `.env`, usando o
  **Session pooler** (porta 5432) com `sslmode=require`.
- Redis: via Docker (`docker run -d -p 6379:6379 redis`) ou Upstash (`rediss://...`).
- Celery no Windows **precisa** de `--pool=solo`.
- Node.js: usado só para compilar o CSS do Tailwind. O `static/css/app.css` compilado vai para o Git,
  então rodar o sistema não exige Node.

## Comandos
```powershell
python manage.py runserver                        # servidor de desenvolvimento
python manage.py makemigrations; python manage.py migrate
python manage.py check                            # validar o projeto
python manage.py test                             # testes
python manage.py popular_demo                     # dados fictícios para demonstração
python manage.py treinar_modelo                   # treina o modelo de evasão e recalcula os riscos
python manage.py calcular_riscos                  # recalcula os riscos com o modelo já treinado
python manage.py gerar_alertas                    # roda agora a rotina diária de alertas (a mesma das 6h)
celery -A config worker --pool=solo -l info       # worker (terminal separado)
celery -A config beat -l info                     # agendador (terminal separado)
npm install                                       # instala o Tailwind (uma vez, em cada computador)
npm run css                                       # compila o CSS (rodar depois de usar classes novas)
npm run css:dev                                   # recompila sozinho a cada alteração (terminal separado)
```

## Stack (exigida pelo professor — não trocar)
django, djangorestframework, django-filter, psycopg2-binary, dj-database-url, python-dotenv,
pandas, openpyxl, scikit-learn, joblib, matplotlib, reportlab, celery, redis, drf-spectacular.
Front-end: templates Django + **Tailwind CSS** (compilado pelo Node: `assets/tailwind.css` gera
`static/css/app.css`) + JavaScript puro (`static/js/portal.js`). Sem React/Vue.

## Estrutura
```
config/            settings.py, urls.py, celery.py
apps/contas/       Usuario customizado, login, redirecionamento e decorators de perfil
apps/academico/    Curso, Turma, Disciplina, Oferta, Matricula, Avaliacao, Nota, Aula, Frequencia, Justificativa, Evento (DER em docs/DER.md)
apps/aluno/        views e templates da área do aluno        → /aluno/
apps/professor/    views e templates da área do professor    → /professor/
apps/coordenacao/  views e templates da área do coordenador  → /coordenacao/
apps/analytics/    gráficos matplotlib e módulo preditivo (scikit-learn)
apps/alertas/      modelo Alerta, notificações e tarefas Celery
apps/relatorios/   geração de PDF (reportlab) e Excel (pandas)
apps/mensagens/    caixa de mensagens interna (mesma tela para os três perfis) → /mensagens/
apps/financeiro/   modelo Mensalidade (extra e simulado; a tela fica em apps/aluno)
apps/api/          serializers, viewsets e rotas da API REST → /api/ e /api/docs/
templates/         esqueleto.html, base.html, 403.html, componentes/ (parciais reutilizáveis)
assets/            tailwind.css (entrada do Tailwind)
static/            css (compilado), js, img
ml/                modelo treinado (.joblib) — não versionar
```

## Regras de autenticação e perfis
- **Não existe tela de cadastro.** Nunca criar rota, link ou botão de "criar conta".
  Contas são criadas pelo coordenador (área de coordenação) ou pelo Django Admin.
- Model `contas.Usuario` (herda `AbstractUser`), `USERNAME_FIELD = "matricula"`,
  campo `perfil` com choices: `ALUNO`, `PROFESSOR`, `COORDENADOR`, `ADMIN`.
  `AUTH_USER_MODEL = "contas.Usuario"` deve existir **antes da primeira migração**.
- Após o login, `/` redireciona conforme o perfil. ADMIN vai para `/admin/`.
- Toda view de área usa o decorator `@perfil_requerido(...)` (ou o mixin equivalente).
  Acesso a área de outro perfil → 403 com página amigável.
- Professor só vê e edita turmas/disciplinas que leciona. Aluno só vê os próprios dados.
- Tela de login: matrícula + senha, "Manter conectado", "Esqueci minha senha"
  (fluxo de redefinição do Django), estados de erro e de carregamento.

## Funções por perfil
- **Aluno:** painel, notas e boletim (PDF), frequência, justificar ausência (com anexo),
  calendário acadêmico, mensagens, financeiro (opcional/extra).
- **Professor:** minhas turmas, lançar notas, chamada com "simulação de biometria",
  avaliar justificativas, gráficos de desempenho da turma, mensagens.
- **Coordenador:** visão geral, alunos em risco de evasão, CRUD de alunos, professores,
  turmas e disciplinas, criação de contas, relatórios PDF/Excel, central de alertas.

## Banco de dados (Supabase)
- O schema é criado **somente pelas migrações do Django**. Não criar tabelas pelo painel
  do Supabase nem por SQL manual. Não apagar migrações já aplicadas.
- O Django conecta com a role `postgres`; não usar a chave `anon`/`service_role` no front-end.
- Nunca colocar senha, URL do banco ou SECRET_KEY no código. Tudo vem do `.env`.
  Manter `.env.example` atualizado (sem valores reais). `.env` está no `.gitignore`.

## Padrão visual (protótipo Figma)
- O nome é sempre **Instituto Socrático** e a logo é um "S", mesmo onde o protótipo mostrar outro
  nome ou outra letra.
- Fonte Inter. Fundo da página `#F5F7FA`, cards brancos com borda `#E5E9F0` e cantos arredondados.
- Azul-marinho da marca `#0B2545` (painel lateral do login, logo "S"); botão primário `#1F4E8C`.
- Selos: verde "Regular", âmbar "Em atenção", vermelho "Em risco".
- Layout das áreas internas: barra lateral à esquerda (logo, menu, card "Precisa de ajuda?",
  "Sair do portal"), topo com breadcrumb, busca, sino de notificações e avatar.
- Responsivo: em telas pequenas a barra lateral vira menu hambúrguer e os cards empilham.
- Ícones: Lucide (via CDN). Componentes repetidos ficam em `templates/componentes/`.

## Gráficos e ML
- Matplotlib com `matplotlib.use("Agg")`; gráficos gerados no servidor e enviados como PNG em base64.
- Evasão: dados simulados gerados por script, modelo `RandomForestClassifier` (ou `LogisticRegression`)
  com features: frequência, média, tendência das notas, justificativas pendentes. Saída: probabilidade
  e nível (baixo/médio/alto) + principais motivos. Recalculado por tarefa Celery agendada.

## Como trabalhar neste projeto
- Trabalhe **uma etapa por vez** (ver "Progresso"). Antes de mudanças grandes, apresente um plano.
- Ao terminar uma etapa: rodar `python manage.py check`, migrações e testes; atualizar a seção
  "Progresso" deste arquivo; sugerir mensagem de commit.
- Prefira código simples e bem comentado: os alunos precisam conseguir explicar tudo na apresentação.
- Se algo exigir decisão (biblioteca nova, mudança de modelo), pergunte antes.

## Progresso
- [x] 1. Base do projeto, `.env`, conexão com Supabase, usuário customizado
  - Decisões: Django 5.2 LTS; testes em SQLite na memória (o sistema usa o Supabase); a rede do SENAI não completa conexões na porta 5432, então usar outra rede (ex.: roteador do celular) para acessar o banco; Data API desligada no painel do Supabase, pois as tabelas do Django não têm RLS (não religar).
- [x] 2. Modelos acadêmicos + Django Admin + comando `popular_demo`
  - Decisões: nome Instituto Socrático com conteúdo de curso superior, como no protótipo; novas entidades `Oferta` e `Aula`; créditos e coeficiente anteriores ficam na `Matricula`; `Usuario.tratamento` é informado no cadastro; média, frequência e selo são calculados em `apps/academico/calculos.py`; anexos ficam em `media/`, sem rota pública.
- [x] 3. Login, redirecionamento por perfil, permissões, `base.html` e layout
  - Decisões: nome trocado para Instituto Socrático, com logo "S"; Tailwind compilado com Node e CSS compilado no Git; ilustração do filósofo nos três estados do login, sem a estatística "25 anos"; "Boas-vindas" no lugar de "Bem-vinda", pois antes do login não sabemos quem entra; item de menu sem tela aparece desativado (`apps/contas/menu.py`); busca e sino ainda são só visuais; link de redefinição de senha vale 1 hora.
- [x] 4. Área do aluno
  - Decisões: apps novos `mensagens` e `financeiro`; a mensagem para a secretaria vai para o primeiro coordenador ativo; Mensagens também ficou ativa no menu do professor e do coordenador, para as conversas terem resposta (o menu do coordenador ganhou esse item); financeiro simulado, com boleto e comprovante desativados; gráfico de notas (etapa 7) e PDF do boletim (etapa 10) ainda não existem, e a tela mostra uma lista e um botão desativado; a análise da justificativa é do professor, então o texto do protótipo que citava a secretaria mudou; várias faltas contam como uma só pendência; anexos ficam na máquina que recebeu o envio e, se faltarem nela, o download responde 404.
- [x] 5. Área do professor
  - Decisões: o protótipo não tem telas do professor, então elas seguem o visual da área do aluno; disciplina de outro professor responde 404; o professor cria avaliações na tela de notas, e elas aparecem no calendário do aluno; campo de nota vazio apaga a nota; a chamada não aceita data futura e exige marcar todos os alunos; a biometria é simulada no navegador (`portal.js`, cerca de 9 em 10 leituras reconhecidas) e falta é sempre gravada como manual; falta que já tem justificativa fica travada na chamada; rejeitar justificativa exige resposta; "Desempenho" fica para a etapa 7; `saudacao`, `texto_dias_ate` e `data_valida` foram para `apps/academico/utilidades.py`; números da turma vêm de `resumo_da_oferta` em `calculos.py`, com as mesmas regras do boletim.
- [x] 6. Área do coordenador (CRUDs e criação de contas)
  - Decisões: o protótipo não tem telas da coordenação, então elas seguem o visual das outras áreas; contas nunca são apagadas pela coordenação, só desativadas (ADMIN fica só no Django Admin, e ninguém desativa a própria conta); conta nova recebe senha provisória aleatória (`secrets`), guardada na sessão e mostrada uma única vez; e-mail obrigatório e único; aluno é criado junto com a matrícula na turma, que só muda enquanto não há notas nem presenças; disciplinas e professores entram na turma pela tela da turma (oferta), e na edição da oferta só o professor muda; turma, disciplina e oferta só são excluídas sem registros ligados (PROTECT + mensagem); turma e disciplina com ofertas não trocam de curso; a situação do aluno na coordenação é a pior entre as disciplinas (`resumo_das_matriculas` em `calculos.py`, 2 consultas para todos os alunos); "Alunos em risco" (etapa 8), "Relatórios" (etapa 10) e "Alertas" (etapa 9) continuam desativados no menu.
- [x] 7. Gráficos com matplotlib
  - Decisões: app novo `analytics` (sem models); cada gráfico devolve `{"png", "descricao"}` ou `None` (estado vazio), e a descrição com os números vai no `alt` (componente `componentes/grafico.html`); usa `matplotlib.figure.Figure` (sem pyplot), fonte padrão do matplotlib (DejaVu Sans) e nenhum cache; aluno: barras no Painel no lugar da lista; professor: tela nova "Desempenho" com a distribuição das médias por faixa (o limite fica na faixa de cima) e a mesma contagem em tabela; coordenação: frequência mensal por turma na Visão geral, só com alunos ativos (no máximo 8 turmas no gráfico); cores testadas para daltonismo, e "7 ou mais" fica azul, porque verde e vermelho se confundem.
- [x] 8. Módulo preditivo de evasão
  - Decisões: risco salvo no model `analytics.RiscoEvasao` (um por matrícula ativa, com probabilidade, nível, motivos e as 4 variáveis usadas), regravado inteiro a cada cálculo em uma transação; `treinar_modelo` gera 2.000 alunos simulados (semente 42) com uma regra logística escondida e treina um RandomForest (200 árvores, profundidade 6), com acurácia de cerca de 81% contra 66% do chute; o caminho do modelo vem de `settings.MODELO_EVASAO` (`ml/modelo_evasao.joblib`); tendência = última nota menos a primeira por disciplina (média entre as disciplinas, 0 sem duas notas); aluno sem nota ou sem chamada fica fora do cálculo; níveis: baixo abaixo de 30%, médio de 30% a 60%, alto a partir de 60%; os motivos são frases montadas com os limites do selo (no máximo 3, números cortados em uma casa para 74,96% não virar "75%"), não vêm do modelo; tela `coordenacao:risco` com botão "Recalcular agora" (POST); o card da Visão geral passou a mostrar as maiores probabilidades (o KPI "Em risco" continua sendo o selo); explicação para a apresentação em `docs/MODELO_EVASAO.md`.
- [x] 9. Alertas automáticos (Celery + Redis)
  - Decisões: app novo `alertas` com o model `Alerta` (destinatário, tipo, gravidade, título, texto, link, chave do assunto, por e-mail, lido em); regras em `apps/alertas/regras.py`: frequência global abaixo de 75% e média abaixo de 6 → aluno, risco de evasão alto → coordenadores ativos, justificativa pendente há mais de 3 dias → professor (um lembrete com o total); avisos na hora pela fila (`transaction.on_commit`) quando o professor publica notas ou avalia justificativa, sem a nota no texto; mesma pessoa + mesma chave não repete em 7 dias; só os alertas "Em risco" vão por e-mail, com até 3 novas tentativas no worker; rotina diária às 6h no `CELERY_BEAT_SCHEDULE` do settings (sem django-celery-beat), que recalcula os riscos e gera os alertas, e sem modelo treinado só a regra de evasão fica de fora; `apps/alertas/fila.py` roda a tarefa na hora se o Redis não responder (cerca de 2 s, com `socket_connect_timeout` 1 e `max_retries` 0); `CELERY_SEM_REDIS=True` no `.env` roda tudo sem fila (máquinas sem Redis, e os testes); Docker não está instalado nas máquinas do SENAI, então a recomendação é o Upstash (`rediss://`, o settings acrescenta `ssl_cert_reqs`); sino com contador e lista (`<details>`), tela `/alertas/` para os três perfis e Central de alertas na coordenação com o botão "Rodar rotina agora"; comando `gerar_alertas`; aviso de mensagem nova no sino, um por conversa (limpo ao abrir a conversa); explicação em `docs/ALERTAS.md`; migrações `alertas/0001` e `0002` já aplicadas no Supabase.
  - Ajustes depois da etapa 9: professor e secretaria (coordenação) também iniciam conversas em Mensagens (professor só com alunos ativos das suas turmas; secretaria com qualquer aluno ativo; a regra antiga era só o aluno iniciar); o boletim do aluno mostra o nome de cada avaliação junto da nota (A1 6,8 · A2 6,5), com a mais recente em destaque (`notas_nomeadas` em `resumo_por_disciplina`).
- [x] 10. Relatórios PDF e Excel
  - Decisões: app novo `relatorios` (sem models); `dados.py` monta o conteúdo uma vez (classes `Relatorio`, `Tabela`, `Coluna`, com os números de `calculos.py`), e `pdf.py` (reportlab/platypus) e `excel.py` (pandas + openpyxl) só desenham; relatórios: boletim (aluno, o próprio, sem número na URL; coordenação, de qualquer matrícula), desempenho da disciplina (professor, só as dele, a de outro dá 404), desempenho da turma, alunos em risco (PDF e Excel) e lista de alunos (só Excel, uma linha por matrícula); `?formato=pdf|xlsx`, outro valor dá 404; filtros com django-filter (`filtros.py`, `django_filters` no `INSTALLED_APPS`), e a tela "Alunos em risco" passou a usar o mesmo `RiscoFiltro`, com a busca pelo nome completo no banco; os botões PDF/Excel das telas levam os filtros da lista; o selo é filtrado depois do cálculo; no PDF os números são cortados em uma casa (como os motivos da etapa 8), e o Excel guarda o valor exato como número, com "(%)" no título das colunas de percentual e nota sem lançamento em branco; Helvetica no PDF, folha deitada nas tabelas largas e gráfico do matplotlib no boletim e no relatório do professor; uma aba por tabela, mais a aba "Sobre o relatório"; gerado na hora, sem Celery (menos de 1 s com os dados de demonstração); tela `relatorios:inicio` ativa no menu da coordenação; explicação em `docs/RELATORIOS.md`.
- [ ] 11. API REST documentada
- [ ] 12. Testes, revisão final e documentação
