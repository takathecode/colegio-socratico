"""Itens da barra lateral de cada perfil.

Uma tela nova entra no menu trocando "rota": None pelo nome da rota dela.
Item com rota None aparece desativado, para nunca existir um link quebrado.
"""

AREAS = {
    "ALUNO": {
        "titulo": "Área do aluno",
        "itens": [
            {"nome": "Painel", "icone": "layout-dashboard", "rota": "aluno:painel"},
            {"nome": "Notas e Boletim", "icone": "chart-no-axes-column", "rota": None},
            {"nome": "Frequência", "icone": "calendar-check", "rota": None},
            {"nome": "Calendário Acadêmico", "icone": "calendar-days", "rota": None},
            {"nome": "Mensagens", "icone": "messages-square", "rota": None},
            {"nome": "Financeiro", "icone": "wallet", "rota": None},
        ],
    },
    "PROFESSOR": {
        "titulo": "Área do professor",
        "itens": [
            {"nome": "Painel", "icone": "layout-dashboard", "rota": "professor:painel"},
            {"nome": "Minhas turmas", "icone": "users", "rota": None},
            {"nome": "Lançar notas", "icone": "square-pen", "rota": None},
            {"nome": "Chamada", "icone": "fingerprint", "rota": None},
            {"nome": "Justificativas", "icone": "file-check", "rota": None},
            {"nome": "Desempenho", "icone": "chart-no-axes-column", "rota": None},
            {"nome": "Mensagens", "icone": "messages-square", "rota": None},
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
        ],
    },
}
