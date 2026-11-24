# Segurança: login, perfis e proteção dos dados

## A ideia em uma frase

Cada pessoa entra com a própria matrícula e só enxerga o que o seu perfil permite: o aluno vê
os próprios dados, o professor só as disciplinas que leciona, a coordenação cuida da parte
acadêmica e a Secretaria só dos acessos (contas e senhas). Isso é conferido no servidor, em
todas as telas, e não só escondendo botões.

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

- **Matrícula e senha.** Não existe tela de cadastro: as contas são criadas pela Secretaria ou
  pelo Django Admin.
- **A senha nunca é guardada.** O banco guarda só o *hash* (PBKDF2, padrão do Django), que não
  dá para desfazer. Nem o administrador consegue ver a senha de ninguém.
- **Senhas fracas são recusadas** pelos validadores (regras abaixo, em "Regras de senha forte").
- **A mesma mensagem para tudo.** Matrícula que não existe, senha errada e conta desativada
  mostram "Matrícula ou senha incorreta". Quem tenta não descobre quais matrículas existem.
- **"Manter conectado"** desmarcado encerra a sessão ao fechar o navegador. Marcado, ela dura
  2 semanas.
- **"Esqueci minha senha"** pede só a matrícula e manda um link que vale 10 minutos e só
  funciona uma vez (detalhes abaixo).

### Bloqueio depois de 5 senhas erradas

Depois de **5 senhas erradas seguidas** na mesma matrícula, o login dela fica bloqueado por
**15 minutos**, mesmo com a senha certa. Isso impede um programa de testar milhares de senhas.

- Os erros ficam no banco (tabela `BloqueioDeLogin`), e não na memória, porque no servidor
  publicado cada pedido pode cair em uma cópia diferente do sistema.
- A contagem é pela **matrícula digitada**, exista ela ou não. Assim o bloqueio também não
  revela quais matrículas existem.
- Erros com mais de 15 minutos não contam, e um login certo zera a contagem.
- Trocar a senha ("Esqueci minha senha", "Alterar minha senha" ou senha provisória da
  Secretaria) desbloqueia na hora. A Secretaria também tem o botão "Desbloquear", e o
  administrador pode apagar o registro no Django Admin.
- O bloqueio fica no backend de autenticação (`apps/contas/backends.py`). Por isso vale
  igualmente para a tela de login, para o token da API e para o Django Admin.

## Perfil Secretaria: só os acessos

A Secretaria (`apps/secretaria/`, endereço `/secretaria/`) é quem cria e cuida das contas. Ela
segue o **princípio do menor privilégio**: faz só o necessário para administrar os acessos.

| A Secretaria pode | A Secretaria não pode |
|---|---|
| Criar contas de aluno, professor e coordenação | Ver notas, frequência, risco de evasão, relatórios ou financeiro (403) |
| Editar nome e e-mail | Usar a API (403, e não recebe token) |
| Enviar link de nova senha ou gerar senha provisória | Alterar contas de administrador, superusuário, staff ou de outra Secretaria |
| Desbloquear o login e desativar ou reativar contas | Apagar contas (só desativa; o histórico continua) |

- **Limite contra escalada de privilégio.** Toda ação busca a conta em
  `servicos.contas_gerenciaveis()` (aluno, professor ou coordenação, sem staff nem
  superusuário). Qualquer outra conta responde **404**, mesmo com o pedido montado à mão. Assim
  ninguém da Secretaria troca a senha de um administrador ou de um colega para entrar no lugar
  dele. Contas de administrador e da Secretaria são cuidadas só pelo Django Admin.
- **Formulários sem campos perigosos.** Não existem os campos perfil, `is_staff` nem
  `is_superuser`: o perfil vem da tela escolhida (aluno, professor ou coordenação). A matrícula
  não muda depois de criada.
- **E-mail obrigatório e único** entre as contas ativas, porque a recuperação de senha depende
  dele. Trocar o e-mail registra quem trocou e **avisa o endereço antigo**: se a troca não foi
  pedida, a pessoa reage. Trocar o e-mail também invalida links antigos.
- **Conferir a identidade.** Antes de redefinir a senha de alguém, a tela avisa: "Confirme a
  identidade da pessoa com documento com foto antes de redefinir". A Secretaria precisa marcar
  "Conferi o documento com foto", e o servidor recusa o pedido sem essa marcação.
- **Duas formas de redefinir:**
  - **Enviar link de redefinição** (recomendada): o mesmo link do "Esqueci minha senha", para o
    e-mail da conta. A Secretaria nunca fica sabendo da senha nova.
  - **Gerar senha provisória**: 12 caracteres sorteados com o módulo `secrets`, que já cumprem
    as regras de senha forte. Ela aparece **uma única vez** (sai da sessão ao abrir a tela),
    para ser entregue pessoalmente. A conta fica com `precisa_trocar_senha`: no próximo login,
    o middleware `apps/contas/middleware.py` leva a pessoa para "Crie a sua senha", e nenhuma
    outra tela abre antes disso (nem a API: com a troca pendente, o token é recusado).

A **coordenação** não cria mais contas nem troca senhas: as rotas antigas foram removidas (o
endereço nem existe). Ela continua com o cadastro acadêmico: matricula o aluno criado pela
Secretaria na turma, liga professores às disciplinas e cuida de turmas e disciplinas.

## "Esqueci minha senha" pela matrícula

Ninguém lembra qual e-mail está na conta, mas todos sabem a matrícula. O fluxo
(`apps/contas/redefinicao.py` e `views.py`) tem quatro etapas, todas com o visual do login:

1. **Matrícula.** A matrícula fica na **sessão** (no servidor), e não na URL: não aparece no
   histórico do navegador nem nos logs.
2. **Confirmação.** Se a conta existe, está ativa e tem e-mail, a tela mostra o e-mail cadastrado
   **mascarado** (`apps/contas/mascara.py`): primeira e última letra do usuário, primeira letra
   do domínio e a terminação, como `f**********a@g****.com`. Senão, uma única mensagem neutra
   ("Não foi possível enviar o link para esta matrícula. Procure a Secretaria da escola."), igual
   para matrícula inexistente, desativada ou sem e-mail.
3. **Verifique seu e-mail**, com o horário exato em que o link deixa de valer e o botão
   "Reenviar".
4. **O link.** Abre a tela "Criar nova senha", com a matrícula travada (só leitura).

**O código do link** (`apps/contas/tokens.py`) é o `PasswordResetTokenGenerator` do Django: uma
assinatura feita com a `SECRET_KEY`, sem nada guardado no banco. Ele deixa de valer quando:

- a senha muda (por isso funciona **uma vez só**);
- a pessoa entra com a senha antiga (o último login faz parte da assinatura);
- o e-mail da conta muda;
- um **link novo é pedido**: o campo `ultimo_pedido_reset` entra na assinatura
  (`_make_hash_value`), então o link anterior perde a validade;
- passam **10 minutos** do pedido (`PASSWORD_RESET_TIMEOUT = 600`).

Outros cuidados:

- O `PasswordResetConfirmView` do Django guarda o código na sessão e troca o endereço por um
  sem o código (`.../set-password/`). As telas mandam `Referrer-Policy: same-origin`, para o
  endereço nunca vazar a outro site.
- A tela não tem campo de matrícula para enviar: a conta é **sempre a do link**. Uma matrícula
  colocada à mão no envio é ignorada.
- Depois da troca: a senha é gravada só como hash (`set_password`), o bloqueio é zerado, a
  troca obrigatória é limpa, o token da API é apagado e **as outras sessões abertas são
  encerradas** (o Django confere o hash da senha a cada pedido). Um e-mail avisa: "Sua senha foi
  alterada em DD/MM/AAAA às HH:MM. Se não foi você, procure a Secretaria imediatamente." Não há
  login automático: a pessoa volta ao login.
- O link do e-mail é montado com o `SITE_URL` do `.env`, nunca com o cabeçalho `Host` do pedido.
  Quem forjasse esse cabeçalho faria o link apontar para um site falso (*host header poisoning*).
- O código do link é criado dentro da tarefa do Celery (`apps/contas/tasks.py`), que recebe só
  o número da conta: o código nunca fica guardado no Redis.

**Limite de pedidos** (tabela `PedidoDeSenha`, no banco porque na Vercel cada pedido pode cair
numa cópia diferente do sistema e a memória não é compartilhada):

| O quê | Limite por hora |
|---|---|
| Links pedidos para a mesma matrícula | 5 |
| Links pedidos do mesmo IP | 10 |
| Matrículas consultadas do mesmo IP | 30 (contra quem tenta descobrir matrículas) |

Acima do limite, a mensagem é neutra. Os pedidos com mais de 1 dia são apagados sozinhos.

> **Por que o banco, e não o `DatabaseCache`?** O `DatabaseCache` precisa do comando
> `createcachetable`, que cria uma tabela fora das migrações. A regra do projeto é que o schema
> vem só das migrações do Django, então o limite ficou num model comum.

## Regras de senha forte

Ficam no `AUTH_PASSWORD_VALIDATORS` do settings, então valem em todo lugar que troca senha: o
link, "Alterar minha senha" (menu do avatar), a troca obrigatória, a senha provisória e o Django
Admin. A checklist da tela (JavaScript) só ajuda a pessoa; **quem decide é o servidor**.

| Regra | Validador |
|---|---|
| De 10 a 128 caracteres | `MinimumLengthValidator` (10) e `ComplexidadeValidator` (128) |
| Letra maiúscula, minúscula, número e caractere especial | `ComplexidadeValidator` (do projeto) |
| Não parecida com a matrícula, o nome ou o e-mail | `UserAttributeSimilarityValidator` |
| Não contém a matrícula, o nome nem parte do e-mail | `DadosPessoaisValidator` (do projeto) |
| Fora da lista de 20 mil senhas comuns | `CommonPasswordValidator` |
| Não pode ser só números | `NumericPasswordValidator` |
| Diferente da senha atual | `DiferenteDaAtualValidator` (do projeto) |

Os validadores do projeto ficam em `apps/contas/senhas.py`, com as mensagens em português.

## Registro de auditoria

Cada ação sensível vira uma linha do model `RegistroDeAuditoria`: **quem fez, em qual conta, qual
ação, data e hora e IP**. Ações registradas: conta criada, dados alterados, e-mail alterado (com
os dois endereços mascarados), link enviado, senha provisória, senha redefinida pelo link, senha
alterada pela própria pessoa, desbloqueio, desativação e reativação.

- **Nunca** guarda senhas nem códigos de link.
- Aparece na tela da conta (Secretaria), na Visão geral de acessos e no Django Admin, que só
  mostra: não cria, não altera e não apaga.
- O IP vem do `REMOTE_ADDR`; na Vercel (`USAR_HTTPS=True`), do cabeçalho `X-Forwarded-For`
  preenchido pelo proxy dela.

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
- O conteúdo do anexo fica no banco (modelo `ArquivoAnexo`, `apps/academico/armazenamento.py`),
  para chegar a quem usa outro computador. Não existe endereço público para ele: o arquivo só é entregue por uma view que
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
- `apps/contas/test_login.py` testa o login, a mesma mensagem para todos os erros e o bloqueio.
- `apps/contas/test_senha.py` testa o "Esqueci minha senha" (máscara, mensagem neutra, limite de
  pedidos, link de uso único, prazo de 10 minutos, link antigo invalidado, link adulterado,
  matrícula forjada no envio), cada regra de senha, a senha provisória e as sessões encerradas.
- `apps/secretaria/tests.py` confere que a Secretaria não altera administrador, staff nem outra
  Secretaria, e que cada ação gera um registro de auditoria sem senha.

## Perguntas que a banca pode fazer

- **"Se eu trocar o número na URL, vejo o boletim de outro aluno?"** Não. O aluno nem tem número
  na URL do boletim (é sempre o dele), e nas outras telas a consulta já filtra pelo usuário: o
  registro de outra pessoa dá 404.
- **"Esconder o botão não basta?"** Não, e o sistema não depende disso: a permissão é conferida
  no servidor. A varredura de permissões testa cada endereço diretamente, sem passar pelos botões.
- **"O bloqueio não deixa alguém travar a conta de um colega de propósito?"** Por 15 minutos,
  sim. É o custo de impedir que alguém teste milhares de senhas. A Secretaria libera na hora
  com o botão "Desbloquear", e a própria pessoa também, trocando a senha pelo link.
- **"Mostrar o e-mail mascarado não revela que a matrícula existe?"** Revela que existe uma
  conta ativa, e isso foi aceito para a pessoa saber para onde o link vai. Por isso há o limite
  de 30 consultas por hora por IP, e o e-mail nunca aparece inteiro.
- **"A Secretaria pode virar administradora?"** Não. Os formulários dela não têm os campos de
  perfil nem de administrador, e as contas de administrador e de outras Secretarias dão 404
  para ela. Isso é conferido no servidor e testado.
- **"Onde fica a senha do banco?"** Só no `.env` de cada computador e nas variáveis do servidor.
  Ela nunca entrou no Git.
