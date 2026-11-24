# Tarefa: perfil "Secretaria" e nova redefinição de senha por matrícula

## Contexto

Você está trabalhando no **Instituto Socrático**, um sistema acadêmico em Django com PostgreSQL (Supabase), Tailwind, Celery/Redis e publicação na Vercel. Leia o `README.md` e o `docs/SEGURANCA.md` antes de começar. Hoje o sistema tem os perfis Aluno, Professor e Coordenação. O login é feito com **matrícula + senha**, e existe um bloqueio de 15 minutos depois de 5 senhas erradas.

Hoje o acesso funciona com estes problemas:

1. A **Coordenação** cria contas e troca a senha de alunos e professores (botão "Nova senha" em `Coordenação → Contas`). Essa tarefa é administrativa e não cabe a ela.
2. A tela de login, a Central de Atendimento e a barra lateral ("Precisa de ajuda? Falar com a secretaria") mandam o usuário procurar a **Secretaria**, mas esse perfil não existe no sistema.
3. Em "Esqueci minha senha", o usuário precisa digitar o **e-mail** cadastrado. Na prática, ninguém sabe qual e-mail está na conta (os e-mails da demonstração são fictícios). O usuário só sabe a **matrícula**.

## Objetivo

1. Criar o perfil **Secretaria**, responsável **somente** pela administração dos acessos de alunos, professores e coordenadores.
2. Refazer o "Esqueci minha senha": o usuário informa a **matrícula**, o sistema mostra o e-mail cadastrado **mascarado** e envia um link seguro. Pelo link, o usuário cria a nova senha numa tela com o mesmo layout do login, onde a matrícula aparece preenchida e não pode ser alterada.
3. Atualizar os textos da Central de Atendimento e da ajuda da barra lateral para a nova dinâmica.

---

## Como trabalhar

1. **Explore antes de mudar.** Localize e leia:
   - o modelo de usuário customizado e o campo de perfil (`apps/contas/`);
   - o decorator `@perfil_requerido` e como cada área é protegida;
   - as views, URLs e templates atuais de login, "Esqueci minha senha", Central de Atendimento e redefinição;
   - a tela `Coordenação → Contas` (listar, editar, nova senha, desativar, criar conta);
   - o layout da tela de login (template base das telas de autenticação) e o componente da barra lateral;
   - a lógica de bloqueio por senhas erradas;
   - o comando `popular_demo` e os testes `apps/contas/test_login.py`, `test_permissoes.py` e `test_telas_demo.py`;
   - a configuração de e-mail em `config/settings.py` e no `.env.example`.
2. **Antes de editar, apresente um plano curto:** os arquivos que vai criar ou alterar, as migrações e as decisões que divergirem deste documento. Depois implemente em etapas, rodando `python manage.py check` e `python manage.py test` ao fim de cada etapa.
3. **Reaproveite o que o Django já oferece** (`PasswordResetTokenGenerator`, `PasswordResetConfirmView`/`SetPasswordForm`, `PasswordChangeView`, `AUTH_PASSWORD_VALIDATORS`, `send_mail`/`EmailMultiAlternatives`). Não reinvente tokens nem a criptografia de senhas.
4. **Siga os padrões do projeto:** nomes em português, as mesmas classes Tailwind e os mesmos componentes de template, mensagens no tom atual das telas. Se usar classes novas do Tailwind, rode `npm run css`.
5. **Não faça:** alterar o `.env`, rodar `migrate` no Supabase sem me perguntar, fazer commit sem eu pedir ou apagar dados reais.

---

## Parte 1: perfil Secretaria

### Modelo e permissões
- Adicione `SECRETARIA` às opções de perfil do usuário, com migração.
- Princípio do menor privilégio: a Secretaria **não** vê notas, frequência, risco de evasão, relatórios acadêmicos nem financeiro. Ela vê apenas a área de acessos.
- Crie a área `/secretaria/`, protegida com `@perfil_requerido` (a varredura de `test_permissoes.py` deve cobrir as rotas novas).
- Barra lateral própria da Secretaria: **Visão geral de acessos**, **Contas**, **Mensagens** e **Sair do portal**.

### O que a Secretaria faz (move a tela de Contas da Coordenação para a Secretaria)
- **Buscar e filtrar contas** (nome, matrícula, perfil, ativas/desativadas), como a tela atual.
- **Criar conta** de aluno, professor e coordenador. O e-mail é obrigatório porque a recuperação de senha depende dele. Valide o formato e mantenha o e-mail único entre as contas ativas.
- **Editar dados de acesso:** nome, e-mail e situação (ativa/desativada). Alterar o e-mail deve registrar quem alterou e avisar o e-mail **antigo** de que houve troca.
- **Redefinir senha de outra pessoa**, com duas opções:
  - **"Enviar link de redefinição"** (recomendada): envia ao e-mail da conta o mesmo link da Parte 2.
  - **"Gerar senha provisória"**: gera uma senha aleatória forte (`secrets`), mostra **uma única vez** na tela para ser entregue pessoalmente e marca a conta para **obrigar a troca no próximo login** (campo como `precisa_trocar_senha`, com migração). Ao entrar, o usuário é redirecionado para a troca e não acessa outra tela até concluir.
  - Antes das duas ações, mostre um aviso: *"Confirme a identidade da pessoa com documento com foto antes de redefinir."*
- **Desbloquear** uma matrícula bloqueada por senhas erradas.
- **Desativar e reativar** contas (o histórico continua guardado).

### Limites para evitar escalada de privilégio
- A Secretaria **não** altera contas de superusuário/staff nem de outros usuários Secretaria. Essas contas são administradas só pelo Django Admin.
- Bloqueie isso **no servidor** (na view ou no form), não apenas escondendo botões, e crie testes para isso.

### Coordenação
- Remova da Coordenação os botões e as rotas de **Nova senha**, **criar conta** e **desativar conta**. Ela continua com o cadastro acadêmico (alunos, professores, turmas, disciplinas).
- Remova o item "Contas" da barra lateral da Coordenação, ou deixe a tela somente leitura. Proponha uma das duas no plano.

### Registro de auditoria
- Registre cada ação sensível (redefinição de senha, senha provisória, troca de e-mail, desbloqueio, desativação): **quem fez, em qual conta, qual ação, data/hora e IP**. **Nunca** registre senhas nem tokens. Mostre esse histórico na tela da conta e no Django Admin.

### Dados de demonstração
- O `popular_demo` deve criar `secretaria01` (senha igual à matrícula, como nas outras contas de demonstração), com um nome fictício.

---

## Parte 2: "Esqueci minha senha" pela matrícula

### Fluxo (telas com o mesmo layout da tela de login)

**Etapa 1: `/senha/esqueci/`**
- Um único campo: **Matrícula** (`autocomplete="username"`), com botão "Continuar" e link "← Voltar para o login".

**Etapa 2: confirmação**
- Se a matrícula existir, estiver **ativa** e tiver e-mail: mostre *"Vamos enviar um link de redefinição para **g\*\*\*\*\*\*7@a\*\*\*\*.senai.br**"* com o botão **"Enviar link"** (POST com CSRF).
- Mostre o e-mail **sempre mascarado**, nunca completo. Mantenha a primeira e a última letra do usuário, a primeira letra do domínio e a terminação (exemplo: `guilherme.j.araujo7@aluno.senai.br` → `g*****************7@a****.senai.br`). Crie uma função utilitária com teste.
- Se a matrícula não existir, estiver desativada ou não tiver e-mail, mostre a mesma mensagem neutra: *"Não foi possível enviar o link para esta matrícula. Procure a Secretaria da escola."* Não diga qual dos três casos aconteceu.
- Não passe a matrícula nem o e-mail pela URL (query string). Guarde a matrícula na sessão entre as etapas 1 e 2.

**Etapa 3: "Verifique seu e-mail"**
- Avise que o link vale por **10 minutos** (mostre o horário exato de expiração, ex.: "válido até 16:21"), sugira olhar a caixa de spam e ofereça "Reenviar" (respeitando o limite de pedidos).

**Etapa 4: `/senha/redefinir/<uidb64>/<token>/` (o link do e-mail)**
- Use `PasswordResetTokenGenerator` (o padrão do `PasswordResetConfirmView`). O token deve ser:
  - de **uso único**: o hash muda depois da troca de senha e do login;
  - **com prazo**: `PASSWORD_RESET_TIMEOUT = 600` (10 minutos). Pedir um link novo invalida o anterior: inclua no hash do token um campo que muda a cada pedido (ex.: `ultimo_pedido_reset`), sobrescrevendo `_make_hash_value` num gerador próprio.
- Como o `PasswordResetConfirmView` já faz, guarde o token na sessão e redirecione para uma URL sem o token, para ele não vazar por histórico ou cabeçalho `Referer`. Use `Referrer-Policy: same-origin` (ou mais restritiva) nessas telas.
- Campos:
  - **Matrícula**: já preenchida e **não editável** (`readonly`, com estilo de campo travado). O servidor **ignora** qualquer matrícula enviada no POST e usa apenas o usuário vindo do token.
  - **Nova senha** e **Confirmar nova senha** (`autocomplete="new-password"`), com o botão de mostrar/ocultar igual ao do login.
  - Uma **checklist ao vivo** dos requisitos (JavaScript como melhoria progressiva). O servidor continua sendo quem decide se a senha é aceita.
- Link inválido ou expirado: tela amigável *"Este link expirou ou já foi usado"*, com botão para pedir outro.

**Depois da troca**
- Salve a senha com `user.set_password()` + `save()`. A senha é gravada no banco **apenas como hash**, nunca em texto puro.
- **Desbloqueie** a matrícula (zere o contador de tentativas) e limpe `precisa_trocar_senha`.
- As outras sessões abertas do usuário devem ser encerradas (o Django faz isso ao mudar o hash da senha; confirme com teste).
- Envie um e-mail de aviso: *"Sua senha foi alterada em DD/MM/AAAA às HH:MM. Se não foi você, procure a Secretaria imediatamente."*
- **Não** faça login automático. Redirecione para o login com a mensagem de sucesso.

### Regras de senha forte (no servidor, em `AUTH_PASSWORD_VALIDATORS`)
Valem para a redefinição, para a troca de senha logado e para a senha provisória:
- No mínimo **10 caracteres** e no máximo 128;
- pelo menos uma letra maiúscula, uma minúscula, um número e um caractere especial (crie um validador customizado com mensagens em português);
- não pode conter a matrícula, o nome nem parte do e-mail (`UserAttributeSimilarityValidator`);
- não pode estar na lista de senhas comuns (`CommonPasswordValidator`) nem ser só números;
- não pode ser igual à senha atual.

### Proteção contra abuso
- **Limite de pedidos** de link: por exemplo, no máximo 5 por matrícula por hora (o prazo curto faz o usuário pedir de novo com mais frequência) e 10 por IP por hora. Acima disso, mostre uma mensagem neutra.
- Use um cache que funcione na Vercel (serverless): o `LocMemCache` não é compartilhado entre instâncias. Use o cache em banco (`DatabaseCache`) ou o Redis já configurado, com o banco como alternativa caso o Redis não esteja disponível.
- Gere o link do e-mail a partir de uma configuração fixa (`SITE_URL` no `.env`, documentada no `.env.example`), **não** do cabeçalho `Host` da requisição, para evitar *host header poisoning*.
- Envie o e-mail pelo Celery quando houver Redis e, sem Redis, na hora (como as outras tarefas do projeto). O tempo de resposta não pode revelar se a matrícula existe.

### E-mail
- Templates em **texto e HTML**, com a identidade visual do portal: o nome do usuário, um botão "Criar nova senha", o link em texto puro como alternativa, o prazo de 10 minutos com o horário exato de expiração e a frase *"Se você não pediu, ignore este e-mail. Sua senha continua a mesma."*
- Em desenvolvimento, continue usando o backend de console. Em produção, use SMTP configurado por variáveis (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`), documentadas no `.env.example` e no `docs/VERCEL.md`.

### Usuário logado
- Adicione **"Alterar minha senha"** no menu do usuário (avatar no topo), para todos os perfis, usando `PasswordChangeView`: pede a senha atual e aplica os mesmos validadores. Use `update_session_auth_hash` para o usuário continuar conectado.

---

## Parte 3: textos e links de ajuda

### Tela de login
- Mantenha "Esqueci minha senha" apontando para o novo fluxo.
- Troque o rodapé por: *"Primeiro acesso ou dificuldade para entrar?"* → **"Fale com a Central de Atendimento"**.

### Central de Atendimento (substitua todo o conteúdo)
Texto curto, em passos, no layout atual:

> **Central de Atendimento**
> Orientações para acessar o portal.
>
> **Primeiro acesso?**
> Sua conta é criada pela Secretaria. Retire na Secretaria sua matrícula e a senha provisória. No primeiro login, o portal pede que você crie sua própria senha.
>
> **Esqueceu a senha?**
> 1. Clique em **Esqueci minha senha** e digite sua matrícula.
> 2. Confira o e-mail mostrado e clique em **Enviar link**.
> 3. Abra o link em até 10 minutos e crie a nova senha.
>
> **Conta bloqueada?**
> Depois de 5 senhas erradas, a matrícula fica bloqueada por 15 minutos. Espere ou redefina a senha: a troca libera o acesso na hora.
>
> **Não recebeu o e-mail ou não usa mais esse endereço?**
> Olhe a caixa de spam. Se não estiver lá, ou se o e-mail estiver errado, vá **pessoalmente à Secretaria da escola** com um documento com foto. Ela atualiza seu e-mail ou redefine sua senha.
>
> ← Voltar ao portal

### Barra lateral (card "Precisa de ajuda?")
- Para aluno, professor e coordenação: *"A Secretaria cuida do seu acesso ao portal."* → **"Falar com a Secretaria"**, abrindo uma nova mensagem em `/mensagens/` já endereçada à Secretaria (verifique se o app de mensagens permite isso; se não permitir, aponte para a Central de Atendimento e me avise).
- Não mostre esse card para a própria Secretaria.

---

## Acessibilidade e boas práticas de interface
- Todo campo com `<label>` associado; erros ligados ao campo por `aria-describedby` e anunciados com `role="alert"`; foco visível; navegação completa pelo teclado.
- A checklist de senha deve ser lida por leitores de tela (`aria-live="polite"`) e não pode depender só de cor.
- O campo de matrícula travado deve continuar legível (contraste AA) e anunciado como somente leitura.
- Botões de envio desativados depois do clique, para evitar duplo envio.
- As telas devem funcionar bem no celular, como a tela de login atual.

---

## Testes obrigatórios
Atualize ou crie os testes (eles continuam em SQLite na memória, sem internet):

- **Permissões:** a varredura inclui as rotas de `/secretaria/`; a Secretaria recebe 403 nas áreas acadêmicas; a Coordenação recebe 403 (ou não tem mais acesso) nas ações de senha e conta; a Secretaria **não** consegue alterar superusuário nem outra Secretaria.
- **Esqueci minha senha:**
  - matrícula válida → e-mail mascarado na tela e um e-mail em `mail.outbox` com o link;
  - matrícula inexistente, desativada ou sem e-mail → mesma mensagem neutra e nenhum e-mail enviado;
  - limite de pedidos respeitado;
  - token funciona uma única vez, expira depois de 10 minutos e o link antigo deixa de valer quando um novo é pedido (use `freezegun` ou `override_settings`) e é rejeitado se adulterado;
  - matrícula enviada no POST é ignorada (não é possível trocar a senha de outra conta);
  - senha fraca é rejeitada por cada regra, com mensagem em português;
  - depois da troca: a senha antiga não funciona, a nova funciona, o bloqueio é zerado, o aviso é enviado e as outras sessões são encerradas.
- **Senha provisória:** obriga a troca no primeiro login, e nenhuma outra tela abre antes disso.
- **Máscara de e-mail:** casos com usuário curto (1 ou 2 letras), subdomínios e letras maiúsculas.
- **Auditoria:** cada ação sensível gera um registro, sem senha nem token.
- **Telas de demonstração:** `test_telas_demo.py` abre todas as telas de `secretaria01`.

---

## Documentação
- **README:** adicione o perfil Secretaria na lista de perfis, a conta `secretaria01` na tabela de acessos de teste, o novo fluxo de "Esqueci minha senha" e as variáveis de e-mail e `SITE_URL`.
- **`docs/SEGURANCA.md`:** perfis e limites da Secretaria, fluxo de redefinição (token, prazo, uso único, máscara, limite de pedidos), regras de senha e auditoria.
- **`.env.example`:** novas variáveis, com comentários no mesmo estilo das existentes.

## Critérios de aceite
- [ ] `python manage.py check` sem avisos e `python manage.py test` passando.
- [ ] `makemigrations` gerado e revisado (não rodar `migrate` no Supabase sem minha confirmação).
- [ ] Com `popular_demo`: `secretaria01` redefine a senha de `aluno01`, `prof01` e `coord01`, mas não a de `admin01`.
- [ ] `aluno01` faz todo o fluxo de "Esqueci minha senha" só com a matrícula, usando o link que aparece no terminal do `runserver`.
- [ ] As telas novas têm o mesmo layout da tela de login e funcionam no celular.
- [ ] Ao final, um resumo com os arquivos alterados, as decisões tomadas e o que ficou pendente.