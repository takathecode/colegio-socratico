# Colégio Socrático — Sistema de Gestão Acadêmica Inteligente

Projeto final do curso de Desenvolvimento de Sistemas (SENAI Morvan Figueiredo).
Sistema em Django com banco PostgreSQL no Supabase e áreas separadas para aluno, professor e coordenador.

> Projeto em desenvolvimento. O andamento das etapas está na seção "Progresso" do `CLAUDE.md`.

## Como instalar no Windows

Requisito: Python 3.12 ou mais novo.

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Se o PowerShell bloquear a ativação do ambiente, rode uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Depois preencha o `.env`. As instruções de cada variável estão no próprio arquivo.

## Como rodar

```powershell
python manage.py migrate
python manage.py runserver
```

Deixe esse terminal aberto: o site só abre enquanto o `runserver` estiver rodando.

O Django Admin fica em http://127.0.0.1:8000/admin/ e o login é feito por matrícula e senha.
Não existe tela de cadastro: as contas são criadas pelo coordenador ou pelo Django Admin.

### Dados de demonstração

```powershell
python manage.py popular_demo
```

Rodar de novo apaga e recria somente os dados de demonstração, com as datas ajustadas para o dia atual.
O comando só funciona com `DEBUG=True`.

### Acessos de teste

A senha é igual à matrícula. Essas contas são somente para desenvolvimento.

| Perfil | Matrícula | Observação |
|---|---|---|
| Administrador | `admin01` | Criada na instalação, com `createsuperuser`; não é recriada pelo `popular_demo` |
| Coordenador | `coord01` | |
| Professor | `prof01` a `prof06` | Um por disciplina |
| Aluno | `aluno01` a `aluno40` | `aluno01` reproduz os dados do protótipo |

Alunos com dados de risco: `aluno05`, `aluno09`, `aluno14`, `aluno18`, `aluno23`, `aluno27`, `aluno32` e `aluno38`.

### Se o sistema travar ao conectar no banco

A rede do SENAI aceita a conexão na porta 5432 do Supabase, mas ela nunca se completa, e o Django
fica parado sem mostrar erro. Nesse caso, conecte o computador a outra rede, como o roteador do celular.

## Testes

```powershell
python manage.py test
```

Os testes usam um banco SQLite em memória. Eles não precisam de internet e não tocam nos dados do Supabase.
