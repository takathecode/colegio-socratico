# Segurança: login, perfis e proteção dos dados

## A ideia em uma frase

Cada pessoa entra com a própria matrícula e só enxerga o que o seu perfil permite: o aluno vê
os próprios dados, o professor só as disciplinas que leciona e a coordenação administra tudo.
Isso é conferido no servidor, em todas as telas, e não só escondendo botões.

## Três perguntas para cada pedido

Todo pedido ao sistema passa por três conferências, nesta ordem:

| Pergunta | Quem responde | Se a resposta for "não" |
|---|---|---|
| 1. A pessoa entrou? | `@login_required` | Vai para a tela de login |
| 2. O perfil dela pode abrir esta tela? | `@perfil_requerido("PROFESSOR")` | Página 403 amigável |
| 3. Este registro é dela? | A consulta ao banco já filtra pelo usuário | 404, como se não existisse |

A terceira pergunta é a mais importante. Exemplo: o professor abre `/professor/turmas/7/`.
A consulta busca a disciplina 7 **entre as do professor** (`servicos.oferta_do_professor`).
Se ela for de outro professor, a resposta é 404. Trocar o número na barra de endereço não
mostra nada de ninguém. O mesmo vale para anexos, conversas, alertas, justificativas e boletins.

O 404 (e não o 403) é de propósito: assim ninguém descobre quais números existem.

## Login

- **Matrícula e senha.** Não existe tela de cadastro: as contas são criadas pela coordenação ou
  pelo Django Admin.
- **A senha nunca é guardada.** O banco guarda só o *hash* (PBKDF2, padrão do Django), que não
  dá para desfazer. Nem o administrador consegue ver a senha de ninguém.
- **Senhas fracas são recusadas** pelos validadores do Django: curtas, só números, comuns ou
  parecidas com o nome.
- **A mesma mensagem para tudo.** Matrícula que não existe, senha errada e conta desativada
  mostram "Matrícula ou senha incorreta". Quem tenta não descobre quais matrículas existem.
- **"Manter conectado"** desmarcado encerra a sessão ao fechar o navegador. Marcado, ela dura
  2 semanas.
- **"Esqueci minha senha"** manda um link que vale 1 hora e só funciona uma vez. Um e-mail que
  não está cadastrado recebe a mesma resposta na tela.

### Bloqueio depois de 5 senhas erradas

Depois de **5 senhas erradas seguidas** na mesma matrícula, o login dela fica bloqueado por
**15 minutos**, mesmo com a senha certa. Isso impede um programa de testar milhares de senhas.

- Os erros ficam no banco (tabela `BloqueioDeLogin`), e não na memória, porque no servidor
  publicado cada pedido pode cair em uma cópia diferente do sistema.
- A contagem é pela **matrícula digitada**, exista ela ou não. Assim o bloqueio também não
  revela quais matrículas existem.
- Erros com mais de 15 minutos não contam, e um login certo zera a contagem.
- Trocar a senha (pela coordenação ou por "Esqueci minha senha") desbloqueia na hora. O
  administrador também pode apagar o registro no Django Admin.
- O bloqueio fica no backend de autenticação (`apps/contas/backends.py`). Por isso vale
  igualmente para a tela de login, para o token da API e para o Django Admin.

## Contas criadas pela coordenação

- A conta nova recebe uma **senha provisória aleatória** (módulo `secrets` do Python), mostrada
  uma única vez.
- Contas **nunca são apagadas**, só desativadas: o histórico de notas e de frequência continua
  existindo. A conta desativada não entra mais nem usa a API.
- Ninguém desativa nem troca a senha da **própria** conta por essa tela.
- Os formulários da coordenação não têm os campos de perfil nem de administrador: um
  coordenador não consegue se transformar em administrador.

## API

- Só consulta (GET). Gravar pela API responde 405.
- Quem não se identificou recebe 401; perfil sem permissão, 403; registro fora do alcance, 404.
- No máximo 10 pedidos de token por minuto, além do bloqueio de senhas erradas.
- **Trocar a senha apaga o token.** Quem tinha copiado o token antigo perde o acesso, como
  acontece com as sessões abertas no navegador.

Detalhes em [API.md](API.md).

## Proteções que o Django já dá (e que o projeto não desliga)

| Ataque | Proteção |
|---|---|
| Formulário falso em outro site enviando dados em nome do usuário (CSRF) | Todo formulário tem `{% csrf_token %}`; nenhuma view usa `csrf_exempt` |
| Código JavaScript escondido em um texto digitado (XSS) | Os templates escapam tudo; o projeto não usa `\|safe` nem `mark_safe` |
| Comandos SQL escondidos em um campo (SQL injection) | Só o ORM do Django; nenhum SQL escrito à mão |
| Link que leva para um site falso depois do login | `next` e os redirecionamentos só aceitam endereços do próprio site |
| Abrir o portal dentro de outro site para enganar cliques | Cabeçalho `X-Frame-Options` (middleware padrão) |

## Anexos (atestados e arquivos das mensagens)

- Só PDF, JPG e PNG, com até 5 MB.
- Não existe endereço público para a pasta `media/`. O arquivo só é entregue por uma view que
  confere o dono (ou o professor da disciplina).
- O arquivo é sempre baixado, nunca aberto dentro do portal. Assim um arquivo malicioso não roda
  no navegador como se fosse parte do site.

## Segredos e banco de dados

- Senha do banco, `SECRET_KEY` e URL do Redis ficam só no `.env`, que está no `.gitignore`. O
  `.env.example` mostra os nomes das variáveis, sem valores.
- O Django conecta ao Supabase pelo servidor, com a role `postgres`. Nenhuma chave do Supabase
  vai para o navegador, e a Data API do Supabase fica desligada: o único caminho até os dados é
  o próprio sistema.

## HTTPS no servidor publicado

Com `USAR_HTTPS=True` no `.env` do servidor:

- os cookies de login só trafegam por HTTPS;
- quem abre em `http://` é levado para `https://`;
- o navegador passa a usar só HTTPS no endereço (HSTS).

No computador fica `False`, porque o `runserver` não tem HTTPS. O comando
`python manage.py check --deploy` confere essa configuração.

## Como isso é testado

- `apps/contas/test_permissoes.py` lê **todas** as rotas do sistema e confere, uma por uma, que o
  visitante vai para o login e que cada perfil errado recebe 403. Se alguém criar uma tela e
  esquecer o `@perfil_requerido`, o teste falha.
- Cada app tem testes de "registro de outra pessoa dá 404" (disciplina de outro professor,
  conversa de outra pessoa, anexo de outro aluno etc.).
- `apps/contas/test_login.py` testa o login, a mesma mensagem para todos os erros, a redefinição
  de senha e o bloqueio.

## Perguntas que a banca pode fazer

- **"Se eu trocar o número na URL, vejo o boletim de outro aluno?"** Não. O aluno nem tem número
  na URL do boletim (é sempre o dele), e nas outras telas a consulta já filtra pelo usuário: o
  registro de outra pessoa dá 404.
- **"Esconder o botão não basta?"** Não, e o sistema não depende disso: a permissão é conferida
  no servidor. A varredura de permissões testa cada endereço diretamente, sem passar pelos botões.
- **"O bloqueio não deixa alguém travar a conta de um colega de propósito?"** Por 15 minutos,
  sim. É o custo de impedir que alguém teste milhares de senhas. A coordenação libera na hora
  gerando uma senha provisória.
- **"Onde fica a senha do banco?"** Só no `.env` de cada computador e nas variáveis do servidor.
  Ela nunca entrou no Git.
