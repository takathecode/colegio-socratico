# API REST

## A ideia em uma frase

Outros sistemas da escola (um aplicativo, a secretaria, a biblioteca) consultam os dados
do Instituto Socrático em JSON, com as mesmas regras de acesso e os mesmos números das telas.
A documentação navegável fica em **`/api/docs/`**.

O enunciado pede "endpoints para consulta de alunos, turmas e relatórios" e "integração com
outros sistemas da escola". Por isso a API **só consulta** (GET). Lançar notas, fazer a
chamada e criar contas continua nas telas, onde já estão as regras de cada operação.

## Bibliotecas

| Biblioteca | Para que serve aqui |
|---|---|
| `djangorestframework` (DRF) | Cria os endpoints: serializers (registro → JSON), viewsets, rotas, permissões, paginação e token. |
| `django-filter` | Filtros pela URL (`?turma=3&nivel=ALTO`). São os mesmos filtros dos relatórios (`apps/relatorios/filtros.py`). |
| `drf-spectacular` | Lê o código da API e gera a documentação OpenAPI (`/api/schema/`) e a tela do Swagger (`/api/docs/`). |

## Como entrar

Toda requisição precisa de login, de um destes dois jeitos:

1. **Sessão do navegador:** quem já entrou no portal abre `/api/` ou `/api/docs/` e usa direto.
2. **Token (outros sistemas):** o sistema troca matrícula e senha por um token e o envia em
   todas as requisições no cabeçalho `Authorization: Token <token>`.

```powershell
# 1) Pedir o token (no PowerShell, use curl.exe; "curl" sozinho é outro comando)
curl.exe -X POST http://127.0.0.1:8000/api/token/ -d matricula=coord01 -d senha=coord01
# {"token":"9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b","perfil":"COORDENADOR"}

# 2) Usar o token
curl.exe -H "Authorization: Token 9944b0..." http://127.0.0.1:8000/api/riscos/?nivel=ALTO

# 3) Sair: apaga o token
curl.exe -X DELETE -H "Authorization: Token 9944b0..." http://127.0.0.1:8000/api/token/
```

No Swagger: `POST /api/token/` → "Try it out" → copie o token → botão **Authorize** →
`tokenAuth` → digite `Token 9944b0...` (com a palavra Token e um espaço antes).

- O token fica na tabela `authtoken_token` (app `rest_framework.authtoken` do DRF).
  Pedir de novo devolve o mesmo token.
- Ele não expira sozinho. Deixa de valer quando é apagado (`DELETE /api/token/` ou o Django
  Admin, em "Tokens") ou quando a coordenação desativa a conta.
- `POST /api/token/` aceita no máximo **10 pedidos por minuto** (throttling do DRF). Depois
  disso, responde 429. Isso dificulta quem tenta adivinhar senhas.
- Contas ADMIN não recebem token: elas usam só o Django Admin, como nas áreas.

## Os endpoints

| Endpoint | Aluno | Professor | Coordenação | O que devolve |
|---|---|---|---|---|
| `GET /api/eu/` | ✔ | ✔ | ✔ | Quem está usando a API |
| `GET /api/cursos/` | ✔ | ✔ | ✔ | Cursos |
| `GET /api/disciplinas/?curso=` | ✔ | ✔ | ✔ | Catálogo de disciplinas |
| `GET /api/turmas/?curso=&semestre=` | as suas | as suas | todas | Turmas |
| `GET /api/turmas/{id}/desempenho/` | 403 | 403 | ✔ | Resumo por aluno e indicadores da turma |
| `GET /api/ofertas/?turma=&disciplina=` | as da sua turma | as que leciona | todas | Disciplina + turma + professor |
| `GET /api/ofertas/{id}/desempenho/` | 403 | só as suas | ✔ | Notas por avaliação, média, frequência e selo de cada aluno |
| `GET /api/matriculas/?busca=&turma=&situacao_matricula=` | a própria | 403 | todas | Alunos, com média geral, frequência global e selo |
| `GET /api/matriculas/{id}/boletim/` | a própria | 403 | ✔ | Boletim: uma linha por disciplina |
| `GET /api/riscos/?nivel=&turma=&busca=` | 403 | 403 | ✔ | Risco de evasão (probabilidade, nível, motivos) |
| `GET /api/riscos/{matrícula}/` | 403 | 403 | ✔ | Risco de uma matrícula |
| `GET /api/relatorios/boletim/{matrícula}/` | a própria | 403 | ✔ | PDF do boletim |
| `GET /api/relatorios/disciplina/{oferta}/?formato=pdf\|xlsx` | 403 | só as suas | ✔ | PDF ou Excel |
| `GET /api/relatorios/turma/{turma}/?formato=pdf\|xlsx` | 403 | 403 | ✔ | PDF ou Excel |
| `GET /api/relatorios/risco/?formato=&nivel=&turma=&busca=` | 403 | 403 | ✔ | PDF ou Excel |
| `GET /api/relatorios/alunos/?formato=xlsx&...` | 403 | 403 | ✔ | Excel |

**Por que "matrículas" e não "alunos"?** Um aluno pode ter mais de uma matrícula (uma por
turma/semestre), e a média, a frequência e o boletim são de cada matrícula. No Swagger, a
seção se chama "Alunos".

**Por que o professor não usa `/api/matriculas/`?** A média geral do aluno mistura as notas
de todas as disciplinas, inclusive as dos outros professores. O professor vê os seus alunos
em `/api/ofertas/{id}/desempenho/`, só na disciplina dele, como na área do professor.

### Listas paginadas

As listas vêm em páginas de 20 itens:

```json
{
  "count": 40,
  "next": "http://127.0.0.1:8000/api/matriculas/?pagina=2",
  "previous": null,
  "results": [ ... ]
}
```

`?pagina=2` muda a página, e `?tamanho=50` muda a quantidade por página (até 100).

### Números

- Notas e percentuais saem como **número** no JSON (`6.75`, `88.89`), com duas casas e sem
  o corte para uma casa do PDF. Quem integra faz as próprias contas.
- O que ainda não existe (nota não lançada, disciplina sem chamada) sai como `null`.
- O selo (`"Regular"`, `"Em atenção"`, `"Em risco"`) é calculado na hora por
  `apps/academico/calculos.py`, como nas telas e nos relatórios.

## Como funciona

```
requisição → autenticação → permissão → escopo → cálculo → serializer → JSON
             token/sessão   o perfil     quais    calculos.py  registro
                            pode usar?   registros             vira JSON
                            (senão 403)  (fora: 404)
```

| Arquivo | Papel |
|---|---|
| `apps/api/permissoes.py` | `so_perfis(...)`: quais perfis usam cada endpoint. `PerfilDoPortal` vale para a API inteira (no settings). |
| `apps/api/escopo.py` | Quais registros cada perfil enxerga (`turmas_visiveis`, `ofertas_visiveis`, `matriculas_visiveis`). |
| `apps/api/serializers.py` | O formato de cada resposta, com a descrição de cada campo (vai para a documentação). |
| `apps/api/views.py` | Os viewsets (listas e detalhes), as ações extras (`desempenho`, `boletim`), o token e os relatórios em arquivo. |
| `apps/api/urls.py` | As rotas. O `DefaultRouter` do DRF cria lista e detalhe de cada viewset sozinho. |
| `apps/api/paginacao.py` | Páginas de 20 itens (`?pagina=`, `?tamanho=`). |

**Permissão (403) e escopo (404) são coisas diferentes.** Permissão responde "o seu perfil
pode usar este endpoint?". Escopo responde "quais registros você enxerga?". Um aluno que
troca o número na URL para ver a matrícula de um colega recebe **404**, como se ela não
existisse. É a mesma regra da área do professor: ninguém descobre se o registro existe.

**Os números são os mesmos das telas.** A API não calcula nada sozinha: chama
`resumo_por_disciplina` (boletim), `resumo_da_oferta` (desempenho da disciplina),
`resumo_da_turma` e `resumo_das_matriculas` (coordenação), as mesmas funções das telas e dos
relatórios. Os arquivos PDF e Excel são os mesmos da etapa 10 (`apps/relatorios/dados.py`).

**Por que os relatórios em arquivo também estão na API?** As telas usam a sessão do
navegador. Pela API, outro sistema baixa o boletim em PDF ou a planilha de risco usando o
token, sem precisar de alguém logado.

## Documentação (drf-spectacular)

- `/api/docs/`: tela do Swagger. Mostra cada endpoint, os filtros e o formato da resposta, e
  tem o botão "Try it out" para testar na hora. A tela é pública (não mostra dados, só como a
  API funciona). Para chamar um endpoint, é preciso estar logado ou usar o Authorize.
- `/api/schema/`: o mesmo conteúdo no formato OpenAPI 3 (YAML), que outras ferramentas leem
  (Postman, Insomnia, geradores de código).
- `/api/`: a "API navegável" do DRF. Logado no portal, dá para clicar nos links e ver o JSON
  formatado.

A documentação sai do próprio código: os textos de `extend_schema(...)` em `views.py` e os
`help_text` dos serializers. Para conferir se ela está completa:

```powershell
python manage.py spectacular --validate --fail-on-warn --file schema.yml
```

## Perguntas que a banca pode fazer

- **"Por que token, e não só login e senha em cada pedido?"** A senha trafega uma vez só, e
  o token pode ser apagado sem trocar a senha. É o jeito padrão do DRF de integrar sistemas.
- **"E o CSRF?"** Ele protege formulários enviados pelo navegador. A API só tem GET, que não
  altera nada. O token não é enviado automaticamente pelo navegador, então não sofre esse
  ataque.
- **"O que impede o professor de ver as notas de outra disciplina?"** O escopo:
  `ofertas_visiveis` só devolve as ofertas dele, então qualquer outra responde 404.
- **"Por que não dá para lançar notas pela API?"** O enunciado pede consulta. Gravação pela
  API exigiria repetir todas as validações da tela (nota de 0 a 10, aluno da turma, chamada
  sem data futura...), e ter as regras em dois lugares aumenta a chance de erro.
