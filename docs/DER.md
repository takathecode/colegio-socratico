# Diagrama de entidades (DER)

Modelos do app `apps/academico` e sua ligação com o usuário do sistema (`contas.Usuario`).

```mermaid
erDiagram
    USUARIO ||--o{ OFERTA : "leciona (professor)"
    USUARIO ||--o{ MATRICULA : "possui (aluno)"
    USUARIO |o--o{ JUSTIFICATIVA : "avalia"
    CURSO ||--o{ DISCIPLINA : "tem"
    CURSO ||--o{ TURMA : "tem"
    TURMA ||--o{ OFERTA : "tem"
    DISCIPLINA ||--o{ OFERTA : "é ofertada em"
    TURMA ||--o{ MATRICULA : "recebe"
    OFERTA ||--o{ AVALIACAO : "tem"
    AVALIACAO ||--o{ NOTA : "gera"
    MATRICULA ||--o{ NOTA : "recebe"
    OFERTA ||--o{ AULA : "tem"
    AULA ||--o{ FREQUENCIA : "registra"
    MATRICULA ||--o{ FREQUENCIA : "tem"
    FREQUENCIA ||--o{ JUSTIFICATIVA : "é justificada por"
    OFERTA |o--o{ EVENTO : "pode ter"

    USUARIO {
        string matricula UK
        string perfil
        string tratamento
        string first_name
        string last_name
        string email
    }
    CURSO {
        string nome UK
        int total_creditos
    }
    DISCIPLINA {
        string codigo UK
        string nome
        int creditos
        int carga_horaria
    }
    TURMA {
        string codigo
        string semestre
        int periodo
    }
    OFERTA {
        bigint turma_id FK
        bigint disciplina_id FK
        bigint professor_id FK
    }
    MATRICULA {
        bigint aluno_id FK
        bigint turma_id FK
        string situacao
        date data_matricula
        int creditos_concluidos
        decimal coeficiente_rendimento
    }
    AVALIACAO {
        bigint oferta_id FK
        string nome
        string tipo
        datetime data_hora
        string local
    }
    NOTA {
        bigint avaliacao_id FK
        bigint matricula_id FK
        decimal valor
        datetime atualizada_em
    }
    AULA {
        bigint oferta_id FK
        date data
        int horas_aula
        string conteudo
    }
    FREQUENCIA {
        bigint aula_id FK
        bigint matricula_id FK
        boolean presente
        string metodo
        datetime registrada_em
    }
    JUSTIFICATIVA {
        bigint frequencia_id FK
        text motivo
        file anexo
        string status
        bigint avaliada_por_id FK
        text resposta
        datetime criada_em
        datetime avaliada_em
    }
    EVENTO {
        string titulo
        string tipo
        datetime inicio
        datetime fim
        string local
        text descricao
        bigint oferta_id FK
    }
```

## Decisões de modelagem

- **Oferta** é uma disciplina em uma turma, com o seu professor. O professor só acessa as ofertas ligadas a ele.
- **Matricula** liga o aluno à turma, e o aluno cursa todas as disciplinas ofertadas nela.
- **Aula** representa uma chamada. **Frequencia** é o log de presença de cada aluno nessa aula.
- **Justificativa** aponta para uma falta real. Mesmo aprovada, ela não altera a frequência.
- **Avaliacao** aparece direto no calendário. **Evento** guarda as demais datas, e um evento sem oferta é institucional.
- **Histórico simplificado:** os semestres anteriores não são cadastrados. Os créditos concluídos e o coeficiente de rendimento ficam na `Matricula`.

## Valores calculados

Média, frequência e selo de situação não são salvos no banco. Eles são calculados em `apps/academico/calculos.py`.

| Valor | Regra |
|---|---|
| Média | Média simples das avaliações lançadas |
| Frequência | Horas presentes ÷ horas de aula dadas |
| Selo "Em risco" | Frequência abaixo de 75% ou média abaixo de 6 |
| Selo "Em atenção" | Frequência abaixo de 80% ou média abaixo de 7 |
| Selo "Regular" | Todos os outros casos |
