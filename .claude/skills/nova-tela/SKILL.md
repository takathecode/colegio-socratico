---
name: nova-tela
description: Use ao criar ou refazer qualquer tela/template HTML do sistema Colégio Socrático (área do aluno, professor ou coordenador), para seguir o protótipo do Figma, o layout padrão e as regras de permissão.
---

# Criar uma tela no padrão Colégio Socrático

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
5. **Visual (Tailwind):** fundo `#F5F7FA`, cards `bg-white border border-[#E5E9F0] rounded-xl p-5`,
   títulos de página `text-2xl font-semibold text-[#0B2545]`, botão primário `bg-[#1F4E8C] text-white`.
   Selos: verde "Regular", âmbar "Em atenção", vermelho "Em risco".
6. **Responsivo:** pense em 375px de largura — grids viram uma coluna, tabelas largas ganham
   `overflow-x-auto` ou viram lista de cards.
7. **Estados:** toda lista precisa de estado vazio; todo formulário precisa de mensagens de erro
   e de sucesso (Django messages) e de botão com estado "carregando".
8. **Menu lateral:** adicione o link na barra lateral do perfil correto e marque como ativo.
9. **Verifique:** `python manage.py check` e confirme que usuários de outros perfis recebem 403.

Se o conector do Figma estiver disponível, consulte a tela correspondente no Figma antes de escrever o HTML.
