Você vai desenvolver comigo, do zero, o TCC "Colégio Socrático — Sistema de Gestão Acadêmica Inteligente".
Leia primeiro, por completo: `CLAUDE.md` (regras do projeto), `docs/TEMA_8.pdf` (enunciado do professor)
e `docs/prototipo/prototipo.png` (protótipo). Tudo o que está no CLAUDE.md é obrigatório.

## Objetivo
Entregar um sistema Django funcional, conectado ao meu banco no Supabase, com login sem cadastro e
áreas separadas para aluno, professor e coordenador, cumprindo todos os módulos do enunciado:
CRUDs, dashboards com matplotlib, módulo preditivo de evasão (scikit-learn), alertas automáticos
(Celery + Redis), relatórios PDF/Excel e API REST documentada.

## Visual: igual ao protótipo
- O Figma é a fonte da verdade: file key `Vg4TMgHDW53cZ7HsbtZUOB` (link no CLAUDE.md).
  Se o MCP do Figma estiver conectado, use-o para ler cada tela (layout, espaçamentos, cores, textos)
  antes de escrever o HTML. Se não estiver, use `docs/prototipo/prototipo.png` e me avise.
- Telas que já existem no protótipo e devem ficar fiéis a ele: Login (normal, erro e carregando),
  Painel do aluno (desktop, menu recolhido e mobile), Notas e Boletim, Frequência com o modal
  "Justificar ausência", Calendário Acadêmico, Mensagens, Financeiro e a biblioteca de componentes.
- Telas do professor e do coordenador ainda não estão no protótipo: crie-as com o mesmo design
  system (mesma barra lateral, topo, cards, tabelas e selos), para parecerem parte do mesmo produto.
- Use sempre a skill `/nova-tela` para criar telas.

## Banco: Supabase
- Projeto ref `rgfnazeqoepnefmjoljc`. O Django se conecta pela `DATABASE_URL` do `.env`
  (Session pooler, porta 5432, `sslmode=require`).
- **Nunca me peça a senha no chat.** Quando chegar a hora, me explique onde copiar a connection
  string no painel do Supabase e espere eu avisar que colei no `.env`.
- Se o MCP do Supabase estiver conectado, use-o só para conferir tabelas e dados, nunca para criar
  ou alterar o schema.

## Como vamos trabalhar
Siga as 12 etapas da seção "Progresso" do CLAUDE.md, **em ordem e uma por vez**:
1. No início de cada etapa, mostre um plano curto (arquivos que vai criar/alterar e decisões).
   Espere meu "ok" antes de escrever código.
2. Implemente a etapa inteira, com código simples e comentado em português.
3. Ao terminar, use a skill `/fechar-etapa` e me diga exatamente **como testar no navegador**
   (URL, usuário de teste e o que devo ver).
4. **Pare e espere** eu testar e responder "próxima etapa". Não avance sozinho.
Se encontrar algo ambíguo ou que dependa de decisão minha, pergunte antes de seguir.

## Usuários de teste
Na etapa 2, o comando `popular_demo` deve criar pelo menos um usuário de cada perfil com senha
simples de teste (ex.: `aluno01`, `prof01`, `coord01`) e listar esses acessos no README.

## Para começar agora
Confirme em poucas linhas que entendeu o projeto, liste o que já existe na pasta e me diga o que
eu preciso instalar no Windows (Python, Git, Docker ou Upstash para o Redis). Depois apresente o
plano da etapa 1.
