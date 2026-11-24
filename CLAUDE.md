# Instituto Socrático — Sistema de Gestão Acadêmica Inteligente (TCC SENAI)

Projeto final do curso de Desenvolvimento de Sistemas (SENAI Morvan Figueiredo).
Sistema acadêmico em Django com banco PostgreSQL hospedado no **Supabase**, quatro áreas
separadas por perfil (aluno, professor, coordenador e Secretaria), dashboards, módulo preditivo de
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
`static/css/app.css`) + JavaScript puro (`static/js/portal.js`; a sala de vídeo usa `static/js/chamada.js`,
carregado pelo bloco `scripts` do `esqueleto.html`). Sem React/Vue.

## Estrutura
```
config/            settings.py, urls.py, celery.py
apps/contas/       Usuario customizado, login, redirecionamento e decorators de perfil
apps/academico/    Curso, Turma, Disciplina, Oferta, Matricula, Avaliacao, Nota, Aula, Frequencia, Justificativa, Evento (DER em docs/DER.md)
apps/aluno/        views e templates da área do aluno        → /aluno/
apps/professor/    views e templates da área do professor    → /professor/
apps/coordenacao/  views e templates da área do coordenador  → /coordenacao/
apps/secretaria/   contas, senhas, desbloqueios e auditoria (só acessos) → /secretaria/
apps/analytics/    gráficos matplotlib e módulo preditivo (scikit-learn)
apps/alertas/      modelo Alerta, notificações e tarefas Celery
apps/relatorios/   geração de PDF (reportlab) e Excel (pandas)
apps/mensagens/    caixa de mensagens interna (mesma tela para todos os perfis do portal) → /mensagens/
apps/videochamadas/ videochamada própria (WebRTC, Jitsi como plano B) entre coordenação e professores → /videochamadas/
apps/financeiro/   modelo Mensalidade (extra e simulado; a tela fica em apps/aluno)
apps/api/          serializers, viewsets e rotas da API REST → /api/ e /api/docs/
templates/         esqueleto.html, base.html, 403.html, componentes/ (parciais reutilizáveis)
assets/            tailwind.css (entrada do Tailwind)
static/            css (compilado), js, img
ml/                modelo treinado (.joblib), versionado para a Vercel (treinou de novo → commit)
```

## Regras de autenticação e perfis
- **Não existe tela de cadastro.** Nunca criar rota, link ou botão de "criar conta" público.
  Contas são criadas pela Secretaria (área `/secretaria/`) ou pelo Django Admin.
- Model `contas.Usuario` (herda `AbstractUser`), `USERNAME_FIELD = "matricula"`,
  campo `perfil` com choices: `ALUNO`, `PROFESSOR`, `COORDENADOR`, `SECRETARIA`, `ADMIN`.
  `AUTH_USER_MODEL = "contas.Usuario"` deve existir **antes da primeira migração**.
- Após o login, `/` redireciona conforme o perfil. ADMIN vai para `/admin/`.
- Toda view de área usa o decorator `@perfil_requerido(...)` (ou o mixin equivalente).
  Acesso a área de outro perfil → 403 com página amigável.
- Professor só vê e edita turmas/disciplinas que leciona. Aluno só vê os próprios dados.
- Tela de login: matrícula + senha, "Manter conectado", "Esqueci minha senha"
  (pela matrícula, com o e-mail mascarado e link de 10 minutos), estados de erro e de carregamento.
- A Secretaria só altera contas de aluno, professor e coordenação sem staff/superusuário
  (`apps/secretaria/servicos.py`); admin, staff e outra Secretaria dão 404 para ela.

## Funções por perfil
- **Aluno:** painel, notas e boletim (PDF), frequência, justificar ausência (com anexo),
  calendário acadêmico, mensagens, financeiro (opcional/extra).
- **Professor:** minhas turmas, lançar notas, chamada com "simulação de biometria",
  avaliar justificativas, gráficos de desempenho da turma, mensagens, videochamada com a coordenação.
- **Coordenador:** visão geral, alunos em risco de evasão, matrícula dos alunos nas turmas,
  professores das disciplinas, turmas e disciplinas, relatórios PDF/Excel, central de alertas,
  videochamada com os professores. Não cria contas nem troca senhas.
- **Secretaria:** só acessos: visão geral de acessos, contas (criar, editar nome/e-mail,
  enviar link de nova senha, senha provisória, desbloquear, desativar/reativar), histórico de
  auditoria e mensagens com alunos. Não vê notas, frequência, riscos, relatórios nem financeiro.

## Banco de dados (Supabase)
- O schema é criado **somente pelas migrações do Django**. Não criar tabelas pelo painel
  do Supabase nem por SQL manual. Não apagar migrações já aplicadas.
- O Django conecta com a role `postgres`; não usar a chave `anon`/`service_role` no front-end.
- Nunca colocar senha, URL do banco ou SECRET_KEY no código. Tudo vem do `.env`.
  Manter `.env.example` atualizado (sem valores reais). `.env` está no `.gitignore`.

## Padrão visual (protótipo Figma)
- O nome é sempre **Instituto Socrático** e a logo é um "S", mesmo onde o protótipo mostrar outro
  nome ou outra letra.
- Cores, raios, sombras, espaços e tamanhos de texto ficam como **tokens** no `@theme` de
  `assets/tailwind.css` (ex.: `bg-fundo`, `border-borda`, `text-marinho`, `text-primaria`, `rounded-cartao`,
  `rounded-controle`, `w-menu`). Nos templates, nada de hex solto; hex só onde o Tailwind não chega
  (e-mails em `templates/contas/email/`, `apps/analytics/graficos.py` e `apps/relatorios/pdf.py`).
- Componentes base em `assets/tailwind.css`: `.cartao`, `.tabela`, `.campo` e `.selo` (+ `selo-ok`,
  `selo-atencao`, `selo-risco`, `selo-info`, `selo-neutro`); KPI sempre pelo `componentes/card_kpi.html`.
  Foco do teclado padrão (contorno azul de 2px) para links, botões e `<summary>`.
- Cabeçalho de página: `<h1 class="titulo-pagina">` + `<p class="subtitulo-pagina">`. Topo e conteúdo param de
  crescer em 1600px (`max-w-topo`/`max-w-pagina` no `base.html`). Nos painéis, a coluna larga empilha
  gráfico e tabelas e a estreita fica com as listas curtas, para não sobrar vazio embaixo das tabelas.
- Animações leves (fim de `assets/tailwind.css`): cards de `main` surgem em sequência (opacidade + 6px,
  `animation-fill-mode: backwards`, para não deixar `transform` preso no card), sino e menu da conta
  abrem deslizando, linha de tabela clareia no hover. Esqueleto de carregamento no `base.html`, ligado
  pelo `portal.js` quando a próxima página demora mais de 300 ms (links internos e filtros GET; downloads
  ficam de fora). Tudo desligado com `prefers-reduced-motion`.
- Fonte Inter. Fundo da página `fundo` (#F5F7FA), cards brancos com borda `borda` (#E5E9F0) e cantos `rounded-cartao`.
- Azul-marinho da marca `marinho` (#0B2545: painel lateral do login, logo "S"); botão primário `primaria` (#1F4E8C).
- Selos: verde "Regular", âmbar "Em atenção", vermelho "Em risco".
- Layout das áreas internas: barra lateral à esquerda (nome do instituto sem o quadrado do "S", menu,
  card "Precisa de ajuda?", "Sair do portal"), topo com breadcrumb, sino de notificações e avatar (a busca geral do topo foi retirada por não ter função; as listas têm busca própria).
  As duas barras flutuam (12px das bordas, cantos arredondados).
- Vidro (glassmorphism) **só nas barras e nos botões**, com CSS `backdrop-filter` (classes `vidro-barra`,
  `botao-vidro` e `botao-vidro-claro` em `assets/tailwind.css`). Cards, tabelas e formulários continuam opacos.
  O `expo-glass-effect` foi descartado: é React Native/iOS e não funciona na web.
- Responsivo: em telas pequenas a barra lateral vira menu hambúrguer e os cards empilham.
  Pensar em 375px. Safe-area do iPhone (`viewport-fit=cover` + utilitários `*-barra-segura` e `pb-segura`
  em `assets/tailwind.css`); em tela de toque (`pointer: coarse`) botões e campos têm no mínimo 44px
  (`--spacing-toque`; nos alvos pequenos, `pointer-coarse:min-h-toque`); campos com 16px no celular
  para o iPhone não dar zoom. O menu do celular atualiza `aria-expanded`, leva o foco para dentro e trava
  a rolagem da página. Tabela com mais de 3 colunas tem, abaixo de `md`, uma lista de cards
  (`<ul class="divide-y divide-borda md:hidden">`) e a tabela fica `hidden md:block`. Botões no fim de
  formulário ficam em `<div class="acoes">` (Cancelar primeiro no HTML): no celular empilham em
  largura cheia, com a ação principal em cima.
- Ícones: Lucide (via CDN). Componentes repetidos ficam em `templates/componentes/`.

## Gráficos e ML
- Matplotlib com `matplotlib.use("Agg")`; gráficos gerados no servidor e enviados como PNG em base64.
  Fonte Inter (arquivos .ttf em `apps/analytics/fontes`, licença OFL, para sair igual na Vercel), cores dos
  tokens da marca e dos selos, PNG com dpi 192 (2× o px do CSS). Cada gráfico devolve também a `largura`
  natural (px do CSS), e `componentes/grafico.html` nunca estica a imagem além dela: assim o texto do
  gráfico fica do tamanho do texto da página (9 pt = 12 px).
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
- [x] 11. API REST documentada
  - Decisões: app novo `api` (sem models) com `rest_framework`, `rest_framework.authtoken` (tabela de tokens, migrações já aplicadas no Supabase) e `drf_spectacular`; a API só consulta (GET, gravação pela API dá 405); login por token (`POST /api/token/` com matrícula e senha, 10 pedidos por minuto; `DELETE` apaga) ou pela sessão do portal, com o token primeiro no settings para quem chega sem login receber 401; ADMIN não recebe token e leva 403; permissão por perfil em `permissoes.py` (`so_perfis`, `PerfilDoPortal` padrão de toda a API, 403) e registros visíveis em `escopo.py` (fora deles, 404); endpoints: `eu`, `cursos`, `disciplinas`, `turmas` (+ `desempenho`, coordenação), `ofertas` (+ `desempenho`, professor só as dele e coordenação), `matriculas` (seção "Alunos": aluno a própria e coordenação; o professor leva 403, porque a média geral mistura as notas de outros professores) + `boletim`, `riscos` (coordenação, endereço pelo número da matrícula, pois o risco é regravado a cada cálculo) e `relatorios/...` (os PDFs e Excel da etapa 10, com `?formato=` e sem negociação de conteúdo, para o Swagger não receber 406); filtros reaproveitam `MatriculaFiltro` e `RiscoFiltro`; números de `calculos.py` (novo `resumo_da_turma`, usado também pelo relatório da turma) saem como número no JSON (`COERCE_DECIMAL_TO_STRING` False), com `null` para o que não existe; paginação de 20 itens (`?pagina=`, `?tamanho=` até 100); Swagger público em `/api/docs/` (versão 5.17.14 fixa no CDN), esquema em `/api/schema/`, conferido com `spectacular --validate --fail-on-warn`; explicação em `docs/API.md`.
- [x] 12. Testes, revisão final e documentação
  - Decisões: a revisão não achou view sem `@perfil_requerido`, registro de outra pessoa acessível, segredo no código, `|safe`, `csrf_exempt` nem SQL cru; falha corrigida: trocar a senha agora apaga o token da API (`Usuario.save()` confere o `_password` do `set_password`), o que vale para a senha provisória, "Esqueci minha senha" e o Admin; bloqueio do login depois de 5 senhas erradas seguidas por 15 minutos (erros com mais de 15 minutos não contam), guardado no banco (model `contas.BloqueioDeLogin`, migração `0003` já aplicada no Supabase), porque na Vercel a memória não é compartilhada entre instâncias; a contagem é pela matrícula digitada, exista ela ou não, para não revelar matrículas; o bloqueio fica no backend `apps/contas/backends.py` (`AUTHENTICATION_BACKENDS`), então vale para o login, o token da API e o Admin; trocar a senha desbloqueia, e o Admin lista e apaga os bloqueios; `USAR_HTTPS` no `.env` liga `SECURE_PROXY_SSL_HEADER` (HTTPS chega pelo proxy da Vercel), cookies seguros, redirecionamento e HSTS de 1 dia, sem subdomínios nem preload (W005 e W021 silenciados), e o `check --deploy` sai limpo; testes novos: varredura de todas as rotas (`test_permissoes.py`: visitante vai ao login, perfil errado e ADMIN recebem 403 em GET e POST, API dá 401/403), fumaça com `popular_demo` + modelo + rotina diária abrindo todas as telas (`test_telas_demo.py`), o modelo acha os 8 alunos de risco da demonstração e piorar uma variável nunca baixa o risco; README virou manual de instalação; explicação em `docs/SEGURANCA.md`.
- [x] 13. Videochamada entre coordenadores e professores
  - Decisões: Jitsi Meet aberto em outra aba (link `target="_blank"`), sem biblioteca, conta nem chave nova; o `iframe` foi descartado porque o meet.jit.si gratuito corta a chamada embutida em 5 minutos, e WebRTC próprio exigiria servidor de sinalização (não existe na Vercel); `JITSI_SERVIDOR` no `.env` (padrão `https://meet.jit.si`); app novo `videochamadas` com o model `Chamada` (quem chamou, convidado, assunto opcional, sala, criada em, encerrada em), que também é o histórico; a chamada é sempre entre um coordenador e um professor, nos dois sentidos, só com contas ativas (`pessoas_para_chamar` + `Chamada.clean()`), e quem chama é sempre quem está logado; nome da sala sorteado com `secrets` (`InstitutoSocratico-` + 24 hexadecimais), e nome da pessoa e assunto vão depois do `#` do link, em JSON; quem não participa recebe 404 (`Chamada.objects.do_usuario`), aluno e ADMIN levam 403; convite no sino (`Alerta.Tipo.VIDEOCHAMADA`, `aviso_de_chamada` em `regras.py`, chave `chamada-<id>`, sem e-mail) gravado na mesma transação da chamada, sem a fila do Celery, porque a chamada é para agora; abrir a sala marca o convite como lido; qualquer um dos dois encerra (POST), e chamada esquecida deixa de estar "em andamento" depois de 3 horas (`DURACAO_MAXIMA`); item "Videochamadas" no menu do professor e da coordenação e botão "Chamar" na lista de professores (só contas ativas, `?para=`); o coordenador aparece com o próprio nome, e não como "Secretaria acadêmica"; migrações `alertas/0003` e `videochamadas/0001` já aplicadas no Supabase; explicação em `docs/VIDEOCHAMADA.md`.
  - Correção depois da etapa 13: o anexo de mensagem não chegava a quem estava em outro computador, porque o arquivo ficava na pasta `media/` da máquina que enviou (o banco é compartilhado, a pasta não). Agora o conteúdo dos anexos (mensagens e justificativas) fica no banco, no model `academico.ArquivoAnexo` (migração `academico/0002`), pelo armazenamento `apps/academico/armazenamento.py` ligado em `STORAGES["default"]`, sem biblioteca nova; anexos antigos ainda são lidos da pasta `media/` local, e `python manage.py migrar_anexos` copia esses arquivos para o banco. Isso também resolve os anexos na Vercel.
  - Videochamada própria, fase 1 de 3 (sinalização e chamada básica), feita depois da etapa 13: sala dentro do portal com WebRTC puro (`static/js/chamada.js`, parcial `_sala_propria.html`), vídeo direto entre os navegadores e nunca gravado; o Django só faz a sinalização por polling HTTP (1 s enquanto conecta, 5 s depois, e na hora se a ligação cair), sem WebSocket nem biblioteca nova, porque a Vercel não segura conexões abertas; model `SinalChamada` (chamada, de, para, tipo entre `entrei`/`oferta`/`resposta`/`candidato`/`saiu`, conteúdo JSON, criado em; índice `(chamada, para, id)`), migração `videochamadas/0002` (já aplicada no Supabase); rotas `sinal/` (GET `?depois=` devolve os sinais para quem pergunta + `encerrada`, 4 consultas com as do login; POST grava para o outro participante, calculado pelo servidor) e `ice/` (STUN `stun:stun.cloudflare.com:3478` sempre; TURN só com `TURN_URLS`, `TURN_USUARIO` e `TURN_SENHA` no `.env`), as duas com `@perfil_requerido`, `do_usuario` (404), `never_cache` e CSRF no cabeçalho `X-CSRFToken`; recusa com 400 chamada fora de andamento, tipo fora da lista, conteúdo que não é objeto e sinal acima de 16 KB; sinais apagados ao encerrar e, com mais de 2 horas, a cada `entrei`; quem criou a chamada sempre faz a oferta; cada aba sorteia uma sessão que vai em todo sinal (recado de aba fechada é ignorado) e a sala começa a ler depois do último sinal existente; os sinais saem em fila, na ordem, e os candidatos de rede vão juntos (200 ms); sem câmera ou sem permissão a pessoa entra só recebendo, com o aviso em português (sem câmera, tenta só o microfone); "Sair da chamada" (aviso `saiu`, a chamada continua) e "Encerrar para os dois"; `VIDEO_MODO=proprio|jitsi` (padrão `proprio`; em `jitsi` a sala antiga volta e `sinal/`/`ice/` dão 404) e o link "Não conectou? Entrar pelo Jitsi" na sala própria; testado também de ponta a ponta com dois Chrome (câmera falsa), incluindo recarregar, sair, encerrar e participante sem câmera; passo a passo do TURN gratuito (Metered) em `docs/VIDEOCHAMADA.md`.
  - Videochamada própria, fase 2 de 3 (controles, chat e reconexão automática): sem mudança no servidor (nenhum model, migração ou rota nova); botões sobre o vídeo para microfone e câmera (`track.enabled`), compartilhar a tela (`getDisplayMedia` + `replaceTrack`, sem renegociar; escondido onde o navegador não compartilha, como no celular) e tela cheia (só o "palco" do vídeo; na tela cheia a mensagem nova aparece por 6 s sobre o vídeo); quem cria a chamada sempre abre os canais de áudio e vídeo de ida e volta, mesmo sem câmera, para quem não tem câmera também compartilhar a tela; chat e estado (microfone, câmera, tela) pelo `RTCDataChannel` "conversa", criado por quem chamou, direto entre os navegadores e nunca gravado (escolha do grupo), texto com `textContent`, 500 caracteres, recado acima de 4 KB ignorado; o outro vê o selo "Microfone desligado", "Compartilhando a tela" ou a foto no lugar do vídeo; conversa ao lado do vídeo em tela `xl` e embaixo dele nas menores; reconexão: com a ligação "desconectada" por 3 s (ou "falhou", na hora, ou quando o computador avisa que a internet voltou), quem chamou refaz a oferta com ICE restart na mesma ligação, até 3 vezes com 10 s entre elas, e o aviso de falha só aparece depois de 35 s; cada oferta leva um `numero` que a resposta repete (resposta de oferta antiga é ignorada); depois de cada oferta ou resposta a tela relê o estado real da ligação, porque do lado que não caiu o navegador não avisa nada; testado de ponta a ponta com dois Chrome headless (câmera falsa): conversa nos dois sentidos, HTML como texto, microfone, câmera, compartilhar tela, reconexão forçada (mesma ligação, vídeo e conversa continuam), recarregar e sair.
  - Videochamada própria, fase 3 de 3 (integração com o portal), com a pré-sala que tinha ficado de fora da fase 2: janela "Fulano está te chamando" (`componentes/chamada_recebida.html`, incluída no `base.html` só para professor e coordenação) com Atender (abre a sala) e Recusar (`POST recusar/` por `fetch`, sem recarregar a página; só o convidado, quem chamou leva 404, chamada atendida ou encerrada dá 400); o `portal.js` pergunta à rota `recebida/` a cada 10 s (30 s com a aba em segundo plano, na hora ao voltar para a aba), 3 consultas por pergunta, e toca a chamada mais recente para a pessoa, sem atendimento nem encerramento, com menos de 2 minutos (`TEMPO_DE_TOQUE`); o título da aba pisca e um bipe sai pelo Web Audio (sem arquivo de som); Esc fecha sem recusar e a janela não volta naquela aba (o fechamento conta pelo evento `close`, porque o Chrome não dispara o `cancel` em janela aberta sem clique); campos `Chamada.atendida_em` e `recusada_em` (migração `videochamadas/0003`, já aplicada no Supabase); atendida = o convidado abriu a sala (vale nos dois modos, também depois dos 2 minutos), recusar também encerra; situação calculada pelas datas (`Chamada.Situacao`: Chamando, Em andamento, Atendida, Recusada, Não atendida) e duração do atendimento ao encerramento (sem duração quando ninguém encerrou); `sinal/` devolve também a situação, e quem chamou vê "Chamando...", "abriu o convite" ou "não atendeu"; pré-sala com prévia da câmera, escolha de câmera e microfone (`enumerateDevices`, guardada no `localStorage` como preferência, não exigência), barra de volume do microfone (`AnalyserNode`) e botões de microfone e câmera (dá para entrar com a câmera desligada), e só "Entrar na sala" manda o `entrei`; Alunos em risco ganhou a coluna "Conversar" com o menu "Chamar professor", só com professores ativos das ofertas da turma do aluno (uma consulta por página, `marcar_professores_para_chamar`), que abre Videochamadas com `?para=` e `?assunto=` preenchidos ("Aluno em risco: Nome (RA ...)", cortado em 120 caracteres), e a chamada só sai em "Chamar agora"; testado também de ponta a ponta com dois Chrome headless (câmera falsa, 39 verificações), mas o Esc foi simulado com `requestClose()`, porque no Chrome headless a tecla não chega à página; o roteiro da fase 2 (agora com a pré-sala) falhou 1 vez em 5 no passo da reconexão forçada, sem causa encontrada (trecho não alterado nesta fase).
  - Ajustes visuais depois da etapa 13: barras flutuantes com vidro (ver "Padrão visual"); o "S" saiu da barra lateral e do topo no celular. Foto de perfil para aluno, professor e coordenação: clicar no avatar do topo abre a janela `componentes/foto_perfil.html`, com as regras de uso (imagem imprópria sujeita a penalização) antes da escolha do arquivo, e o campo só é liberado depois da confirmação (o servidor também exige o `aceite`); campo `Usuario.foto` (migração `contas/0004`, com `db_default=""` para o código antigo continuar criando contas), conteúdo no banco (`ArquivoAnexo`), nome sorteado, JPG/PNG/WebP até 2 MB conferidos pelos primeiros bytes (`apps/contas/foto.py`, sem Pillow), entregue por `contas:foto` (a própria) e `contas:foto_de` (a de outra conta, com a regra `pode_ver_foto` em `foto.py`: sem hierarquia, qualquer conta logada no portal vê a foto de qualquer outra; só a do ADMIN dá 404), cache privado com `?v=`, e aparece na sala e no histórico de videochamadas, nas listas de contas e de professores da coordenação e nas Mensagens (sem foto, a secretaria aparece como "SA"); o `portal.js` recorta em quadrado, reduz para 512×512 e regrava em JPEG antes do envio, o que também apaga o EXIF (localização GPS); a foto não aparece no Admin nem na API. Migração `contas/0004` já aplicada no Supabase.
  - Perfil Secretaria e "Esqueci minha senha" pela matrícula, feitos depois da etapa 13 (pedido em `SECRETARIA.md`): perfil `SECRETARIA` e app novo `secretaria` (`/secretaria/`: Visão geral de acessos, Contas, tela da conta com histórico, criar conta de aluno/professor/coordenação, editar nome e e-mail, "Enviar link de redefinição" ou "Gerar senha provisória" com a marcação obrigatória "Conferi o documento com foto", desbloquear, desativar/reativar); a Secretaria só altera contas de `servicos.contas_gerenciaveis()` (aluno, professor e coordenação sem staff nem superusuário), e admin, staff e outra Secretaria dão 404; formulários sem perfil/is_staff/is_superuser e matrícula fixa depois de criada; e-mail obrigatório e único entre as contas ativas (o de conta desativada pode ser reaproveitado, e reativar com e-mail em uso é recusado); trocar o e-mail avisa o endereço antigo (`avisar_troca_de_email`) e invalida links antigos; a Secretaria leva 403 nas áreas acadêmicas e na API (e não recebe token); a coordenação perdeu "Contas", criar conta, nova senha, desativar e editar professor (as rotas não existem mais), e a edição do aluno virou "Matrícula do aluno" (turma e situação; aluno criado pela Secretaria sem turma aparece com "Matricular"); senha provisória (12 caracteres, `secrets`, já cumpre as regras) liga `Usuario.precisa_trocar_senha`, e o middleware `apps/contas/middleware.py` só deixa abrir "Crie a sua senha" e "Sair" (o token da API também é recusado); auditoria no model `contas.RegistroDeAuditoria` (quem, conta, ação, data/hora, IP; nunca senha nem código; e-mails mascarados no detalhe), mostrada na tela da conta, na visão geral e no Admin (só leitura); "Esqueci minha senha" em 4 etapas com o layout do login: matrícula (guardada na sessão, nunca na URL), e-mail cadastrado mascarado (`apps/contas/mascara.py`: primeira e última letra do usuário, primeira letra do domínio e o que vem depois do primeiro ponto) ou a mesma mensagem neutra para inexistente/desativada/sem e-mail, "Verifique seu e-mail" com o horário exato e "Reenviar", e o link `/senha/redefinir/<uidb64>/<token>/` (`RedefinirSenhaView`, filha do `PasswordResetConfirmView`, matrícula travada sem `name`, checklist ao vivo em `portal.js`, sem login automático); token `GeradorDeLinkDeSenha` (`apps/contas/tokens.py`) com `ultimo_pedido_reset` no hash (link novo invalida o anterior) e prazo contado do pedido, `PASSWORD_RESET_TIMEOUT = 600`; `Referrer-Policy: same-origin` nessas telas (`no-referrer` foi descartado: faz o navegador mandar `Origin: null` e o CSRF recusa os formulários); limite por hora no model `contas.PedidoDeSenha` (5 links por matrícula, 10 por IP, 30 consultas por IP; no banco, e não no `DatabaseCache`, porque o `createcachetable` cria tabela fora das migrações); e-mails em texto e HTML (`templates/contas/email/`) pelas tarefas de `apps/contas/tasks.py` (o código do link é criado no worker e nunca passa pelo Redis), com o link montado do `SITE_URL` (novo no `.env`; `ENDERECO_DO_SITE` continua aceito); depois da troca: hash, desbloqueio, fim da troca obrigatória, outras sessões encerradas e e-mail "Sua senha foi alterada em..."; validadores novos em `apps/contas/senhas.py` (10 a 128 caracteres, maiúscula, minúscula, número e especial; não contém matrícula, nome nem e-mail; diferente da atual) além dos do Django; "Alterar minha senha" no menu do avatar (agora um `<details>` com "Foto de perfil" e "Alterar minha senha"); SMTP por `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`EMAIL_USE_TLS` (timeout 10 s); Central de Atendimento reescrita; card "Precisa de ajuda?": aluno abre mensagem já endereçada à Secretaria, professor e coordenação vão à Central (toda conversa tem um aluno de um dos lados), e a Secretaria não vê o card; em Mensagens, a Secretaria atende como "Secretaria acadêmica" (sem conta de Secretaria, o primeiro coordenador ativo responde) e o coordenador passa a aparecer com o próprio nome; erros dos campos ligados por `aria-describedby` e `role="alert"`; `popular_demo` cria `secretaria01` (Sônia Martins), que também assina a conversa "Atualização dos seus dados cadastrais"; testes novos em `apps/contas/test_senha.py` e `apps/secretaria/tests.py` (478 no total), sem biblioteca nova (o tempo é adiantado com `unittest.mock`); migrações `contas/0005` e `mensagens/0002` já aplicadas no Supabase; explicação em `docs/SEGURANCA.md`.
  - Correções depois do merge na `main`: o "Esqueci minha senha" dava 403 de CSRF no navegador (Vercel e local), porque `Referrer-Policy: no-referrer` faz o navegador mandar `Origin: null` nos POST e o CSRF do Django recusa; agora é `same-origin` (o endereço só vai para o próprio portal), com o teste `test_formularios_passam_pelo_csrf_do_navegador`, que manda o Origin como o navegador faria (o cliente de testes do Django não manda); no Windows o relógio avança de poucos em poucos milissegundos e dois pedidos seguidos geravam o mesmo link, então o `ultimo_pedido_reset` sempre avança (no mínimo 1 µs, com `select_for_update` dentro de `transaction.atomic`); sem SMTP os e-mails não chegam a ninguém (backend de console), então `apps/contas/envio_de_email.py` diz se a entrega é de verdade: a tela da conta na Secretaria avisa e sugere a senha provisória, a mensagem depois de "Enviar link" deixa de dizer "enviado" no servidor publicado, o `check` mostra `contas.W001` com `DEBUG=False` e cada envio sem SMTP deixa um aviso no log.
  - Front-end em 8 etapas (branch `felippe`, commits `feat(front-1..8)`), mesma stack, sem biblioteca nova: tokens
    de design no `@theme` (cores, raios, espaços, textos; nada de hex solto nos templates); componentes base
    (`.cartao`, `.tabela`, `.campo`, `.selo`, `.acoes`, `.titulo-pagina`, KPI sempre pelo `card_kpi.html`) e foco do
    teclado padrão; mobile (safe-area do iPhone, toque de 44px em tela de toque, campos de 16px, menu com
    `aria-expanded` e foco, tabelas largas viram cards abaixo de `md`, botões de formulário empilhados); desktop
    (título de 28px, conteúdo limitado a 1600px, painel da coordenação com gráfico e turmas na coluna larga);
    animações leves com `prefers-reduced-motion` e esqueleto de carregamento na navegação; gráficos com a fonte
    Inter (arquivos em `apps/analytics/fontes`) e sem esticar além do tamanho natural; revisão: `slate-500` do tema
    escurecido para `#56677F`, porque o original dava 4,44:1 sobre o fundo (WCAG AA pede 4,5), e nenhum texto ficou
    abaixo de 4,5:1 nas 28 telas auditadas; 31 telas sem rolagem lateral em 375, 768 e 1280 px (emulação no
    Chrome). O vidro continua só nas barras e nos botões.
- [ ] 14. Publicação na Vercel (configuração pronta; falta criar o projeto na Vercel e publicar)
  - Decisões: suporte nativo da Vercel ao Django (detecta o `manage.py` e usa o `WSGI_APPLICATION`), sem `builds`/`routes` e sem biblioteca nova; `STATIC_ROOT = staticfiles/` faz a Vercel rodar o `collectstatic` no build e servir pelo CDN (sem WhiteNoise); `CELERY_SEM_REDIS=True` na Vercel e rotina das 6h pelo Cron do `vercel.json` (`0 9 * * *` UTC) chamando `GET /tarefas/rotina-diaria/` (`apps/alertas/cron.py`, fora de namespace e da varredura de permissões, com testes próprios em `test_cron.py`), protegido por `Authorization: Bearer <CRON_SECRET>` com `secrets.compare_digest` e 404 sem segredo ou com `CRON_SECRET` vazio; modelo `ml/modelo_evasao.joblib` versionado (1,3 MB, mesma versão do scikit-learn do `requirements.txt`); `DATABASE_URL` na porta 6543 (Transaction pooler) liga `CONN_MAX_AGE=0` e `DISABLE_SERVER_SIDE_CURSORS`; `VERCEL_URL` e `VERCEL_PROJECT_PRODUCTION_URL` entram sozinhos no `ALLOWED_HOSTS`; `maxDuration` 60 s; Python 3.12 (`.python-version`); migrações continuam sendo aplicadas do computador; o `Claude Setup.exe` que entrou por engano no commit "Ajustes" saiu do repositório (`*.exe` no `.gitignore`); passo a passo e variáveis em `docs/VERCEL.md`. E-mail real depende de um SMTP (sem ele, só no log).
