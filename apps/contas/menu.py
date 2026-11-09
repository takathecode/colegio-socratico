"""Itens da barra lateral de cada perfil.

Uma tela nova entra no menu trocando "rota": None pelo nome da rota dela.
Item com rota None aparece desativado, para nunca existir um link quebrado.
"tambem_ativo" lista outras rotas que mantêm o item marcado (ex.: formulário com erro).
"""

MENSAGENS = {
    "nome": "Mensagens",
    "icone": "messages-square",
    "rota": "mensagens:caixa",
    "tambem_ativo": ("mensagens:responder", "mensagens:nova"),
}

AREAS = {
    "ALUNO": {
        "titulo": "Área do aluno",
        "itens": [
            {"nome": "Painel", "icone": "layout-dashboard", "rota": "aluno:painel"},
            {"nome": "Notas e Boletim", "icone": "chart-no-axes-column", "rota": "aluno:notas"},
            {"nome": "Frequência", "icone": "calendar-check", "rota": "aluno:frequencia"},
            {"nome": "Calendário Acadêmico", "icone": "calendar-days", "rota": "aluno:calendario"},
            MENSAGENS,
            {"nome": "Financeiro", "icone": "wallet", "rota": "aluno:financeiro"},
        ],
    },
    "PROFESSOR": {
        "titulo": "Área do professor",
        "itens": [
            {"nome": "Painel", "icone": "layout-dashboard", "rota": "professor:painel"},
            {
                "nome": "Minhas turmas",
                "icone": "users",
                "rota": "professor:turmas",
                "tambem_ativo": ("professor:turma",),
            },
            {"nome": "Lançar notas", "icone": "square-pen", "rota": "professor:notas"},
            {"nome": "Chamada", "icone": "fingerprint", "rota": "professor:chamada"},
            {
                "nome": "Justificativas",
                "icone": "file-check",
                "rota": "professor:justificativas",
                "tambem_ativo": ("professor:avaliar_justificativa",),
            },
            # Os gráficos de desempenho da turma são feitos na etapa 7.
            {"nome": "Desempenho", "icone": "chart-no-axes-column", "rota": None},
            MENSAGENS,
        ],
    },
    "COORDENADOR": {
        "titulo": "Área da coordenação",
        "itens": [
            {"nome": "Visão geral", "icone": "layout-dashboard", "rota": "coordenacao:painel"},
            {"nome": "Alunos em risco", "icone": "triangle-alert", "rota": None},
            {"nome": "Alunos", "icone": "graduation-cap", "rota": None},
            {"nome": "Professores", "icone": "users", "rota": None},
            {"nome": "Turmas", "icone": "school", "rota": None},
            {"nome": "Disciplinas", "icone": "book-open", "rota": None},
            {"nome": "Contas", "icone": "key-round", "rota": None},
            {"nome": "Relatórios", "icone": "file-text", "rota": None},
            {"nome": "Alertas", "icone": "bell-ring", "rota": None},
            MENSAGENS,  # os coordenadores respondem como "Secretaria acadêmica"
        ],
    },
}
