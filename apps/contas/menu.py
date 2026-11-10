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

# Só a coordenação e os professores fazem videochamadas (o aluno não participa).
VIDEOCHAMADAS = {
    "nome": "Videochamadas",
    "icone": "video",
    "rota": "videochamadas:inicio",
    "tambem_ativo": ("videochamadas:sala", "videochamadas:nova"),
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
            {"nome": "Desempenho", "icone": "chart-no-axes-column", "rota": "professor:desempenho"},
            MENSAGENS,
            VIDEOCHAMADAS,
        ],
    },
    "COORDENADOR": {
        "titulo": "Área da coordenação",
        "itens": [
            {"nome": "Visão geral", "icone": "layout-dashboard", "rota": "coordenacao:painel"},
            {"nome": "Alunos em risco", "icone": "triangle-alert", "rota": "coordenacao:risco"},
            {
                "nome": "Alunos",
                "icone": "graduation-cap",
                "rota": "coordenacao:alunos",
                "tambem_ativo": ("coordenacao:aluno_novo", "coordenacao:aluno_editar"),
            },
            {
                "nome": "Professores",
                "icone": "users",
                "rota": "coordenacao:professores",
                "tambem_ativo": ("coordenacao:professor_novo", "coordenacao:professor_editar"),
            },
            {
                "nome": "Turmas",
                "icone": "school",
                "rota": "coordenacao:turmas",
                "tambem_ativo": (
                    "coordenacao:turma_nova",
                    "coordenacao:turma",
                    "coordenacao:turma_editar",
                    "coordenacao:turma_excluir",
                    "coordenacao:oferta_editar",
                    "coordenacao:oferta_excluir",
                ),
            },
            {
                "nome": "Disciplinas",
                "icone": "book-open",
                "rota": "coordenacao:disciplinas",
                "tambem_ativo": (
                    "coordenacao:disciplina_nova",
                    "coordenacao:disciplina_editar",
                    "coordenacao:disciplina_excluir",
                ),
            },
            {
                "nome": "Contas",
                "icone": "key-round",
                "rota": "coordenacao:contas",
                "tambem_ativo": (
                    "coordenacao:coordenador_novo",
                    "coordenacao:coordenador_editar",
                    "coordenacao:senha_provisoria",
                ),
            },
            {"nome": "Relatórios", "icone": "file-text", "rota": "relatorios:inicio"},
            {"nome": "Alertas", "icone": "bell-ring", "rota": "coordenacao:alertas"},
            MENSAGENS,  # os coordenadores respondem como "Secretaria acadêmica"
            VIDEOCHAMADAS,
        ],
    },
}
