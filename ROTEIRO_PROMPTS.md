# Roteiro de prompts — Claude no VS Code

Antes de tudo: abra a pasta do projeto no VS Code (com `CLAUDE.md` e a pasta `.claude` na raiz).
O Claude lê o `CLAUDE.md` sozinho, então os prompts abaixo podem ser curtos.

Dica: para etapas grandes, ative o **modo de plano** antes de enviar o prompt. O Claude mostra o
plano primeiro e só escreve código depois que você aprovar.

---

## Etapa 1 — Base do projeto e conexão com o Supabase
> Leia o CLAUDE.md. Vamos fazer a etapa 1. Crie o projeto Django `config` na raiz, a pasta `apps/`,
> o app `contas` com o model `Usuario` customizado, settings lendo o `.env` (DATABASE_URL, SECRET_KEY,
> DEBUG), `.env.example`, `.gitignore` e `requirements.txt`. Ainda **não** rode o migrate: me diga
> como pegar a connection string no Supabase e onde colar, e espere eu confirmar.

Depois que você colar a `DATABASE_URL` no `.env`:
> Já preenchi o .env. Rode o migrate, crie um superusuário de teste e confirme que as tabelas foram
> criadas no Supabase. Depois use /fechar-etapa.

## Etapa 2 — Modelos acadêmicos
> Etapa 2. Proponha o DER (modelos e relacionamentos) antes de escrever código. Depois de eu aprovar,
> crie os modelos, registre no Admin e crie o comando `popular_demo` com 1 coordenador, 6 professores,
> 2 turmas e 40 alunos fictícios com notas e frequência (alguns propositalmente em risco).

## Etapa 3 — Login e perfis
> Etapa 3. Crie a tela de login igual ao protótipo (anexo a imagem), sem opção de cadastro, o
> redirecionamento por perfil, o decorator `perfil_requerido`, a página 403 e o `base.html` com
> barra lateral e topo. Use /nova-tela.

## Etapas 4, 5 e 6 — Áreas de cada perfil (uma tela por prompt!)
> Etapa 4. Use /nova-tela para criar o Painel do aluno igual à imagem anexa.

Repita com cada tela: Notas e Boletim, Frequência (com modal de justificativa), Calendário,
Mensagens... Depois faça o mesmo para professor e coordenador.

## Etapa 7 — Gráficos
> Etapa 7. Crie em `apps/analytics/graficos.py` funções matplotlib para: notas por disciplina (aluno),
> distribuição de notas da turma (professor) e evolução da frequência (coordenador). Mostre-os nas telas.

## Etapa 8 — Módulo preditivo
> Etapa 8. Crie o comando `treinar_modelo` (dados simulados + RandomForest) e uma função que calcula
> o risco de evasão de cada aluno. Crie a tela "Alunos em risco" do coordenador. Explique o modelo em
> linguagem simples para usarmos na apresentação.

## Etapa 9 — Alertas (Celery + Redis)
> Etapa 9. Configure Celery + Redis no Windows. Crie tarefas: recalcular riscos toda noite, alertar
> quando frequência < 75% ou nota < 6 e enviar e-mail (em desenvolvimento, backend de console).
> Mostre os alertas no sino de notificações. Me explique como subir o Redis.

## Etapa 10 — Relatórios
> Etapa 10. Boletim do aluno em PDF (reportlab) e relatório da turma/escola em PDF e Excel (pandas).

## Etapa 11 — API REST
> Etapa 11. Crie a API com DRF + django-filter para alunos, turmas, notas e relatórios de risco,
> com permissões por perfil e documentação Swagger em /api/docs/.

## Etapa 12 — Revisão final
> Etapa 12. Revise o projeto inteiro procurando falhas de permissão, senhas no código e erros.
> Escreva testes para login, permissões e o módulo preditivo. Gere o README com manual de instalação.

---

## Quando algo der errado
> Rodei [comando] e deu este erro: [cole o erro completo]. Descubra a causa antes de alterar o código.

Regras de ouro:
- **Uma etapa por vez.** Não peça "o sistema inteiro" num prompt só.
- Ao terminar cada etapa, faça commit no Git. Se o Claude estragar algo, é só voltar.
- Leia o que ele fez. Na apresentação, o professor vai perguntar sobre o código.
- Nunca cole a senha do banco no chat; ela fica só no `.env`.
