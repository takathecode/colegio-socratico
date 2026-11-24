---
name: nova-tela
description: Use ao criar ou refazer qualquer tela/template HTML do sistema Instituto Socrático (área do aluno, professor ou coordenador), para seguir o protótipo do Figma, o layout padrão e as regras de permissão.
---

# Criar uma tela no padrão Instituto Socrático

Siga estes passos sempre que for criar ou alterar uma tela.

1. **Confirme o perfil e a rota.** A tela pertence a qual área (`aluno`, `professor`,
   `coordenacao`)? A URL fica no `urls.py` do app daquela área, com `app_name` definido.
2. **View protegida.** Use `@login_required` + `@perfil_requerido("PERFIL")`. Filtre os dados
   pelo usuário logado (aluno vê só os próprios dados; professor só as turmas que leciona).
   Use `select_related`/`prefetch_related` para evitar consultas repetidas no Supabase.
3. **Template.** Estenda `templates/base.html` e preencha os blocos `titulo`, `breadcrumb`
   e `conteudo`. Salve em `apps/<area>/templates/<area>/<nome>.html`.
4. **Reaproveite componentes** de `templates/componentes/` antes de criar novos:
   card de indicador (`card_kpi.html`), selo de situação (`selo.html`), tabela (`tabela.html`),
   modal (`modal.html`), estado vazio (`vazio.html`). Se criar um componente novo, coloque lá.
5. **Visual (Tailwind):** use os tokens do `@theme` de `assets/tailwind.css`, nunca hex soltos
   (`text-[#...]`). Componentes base (também em `assets/tailwind.css`): card `cartao p-5`,
   tabela `<table class="tabela">` (sem classes repetidas em `th`/`td`), campo `campo h-10 w-full`
   (ou `CLASSES_CAMPO` nos forms), selo `selo selo-ok|selo-atencao|selo-risco|selo-info|selo-neutro`
   e indicador `componentes/card_kpi.html` (valor composto vem pronto da view).
   Fundo `bg-fundo`,
   títulos de página `text-2xl font-semibold text-marinho`, botão primário `botao-vidro rounded-controle text-white`,
   botão secundário `botao-vidro-claro rounded-controle text-primaria` (classes de vidro em `assets/tailwind.css`).
   Cor ou medida nova que se repete vira token no `@theme`. Hex só onde o Tailwind não chega
   (e-mails, matplotlib e reportlab).
   O vidro é só para barras e botões: cards, tabelas e formulários continuam brancos e opacos.
   Selos: verde "Regular", âmbar "Em atenção", vermelho "Em risco".
   O nome é sempre Instituto Socrático e a logo é "S", mesmo que o protótipo mostre outro nome.
6. **Responsivo:** pense em 375px de largura — grids viram uma coluna, tabelas largas ganham
   `overflow-x-auto` ou viram lista de cards.
7. **Estados:** toda lista precisa de estado vazio; todo formulário precisa de mensagens de erro
   e de sucesso (Django messages) e de botão com estado "carregando".
8. **Menu lateral:** adicione o link na barra lateral do perfil correto e marque como ativo.
9. **Verifique:** rode `npm run css` (classes novas só funcionam depois de compilar),
   `python manage.py check` e confirme que usuários de outros perfis recebem 403.

Se o conector do Figma estiver disponível, consulte a tela correspondente no Figma antes de escrever o HTML.
