# Videochamada entre coordenação e professores

## A ideia em uma frase

O coordenador chama um professor (ou o professor chama a coordenação) com um clique: o portal
cria uma sala no **Jitsi Meet**, avisa a outra pessoa pelo sino e guarda o histórico. O aluno
não participa.

## Por que o Jitsi, aberto em outra aba

O vídeo não passa pelo nosso servidor. Fazer vídeo "do zero" (WebRTC) exige um servidor de
sinalização sempre ligado, que troca as mensagens entre os navegadores, e isso não combina com
a Vercel, onde o sistema fica desligado entre um pedido e outro. O Jitsi Meet já faz essa parte:
é gratuito, de código aberto, roda no navegador e não exige biblioteca nova no projeto.

| Opção | Por que não escolhemos |
|---|---|
| WebRTC próprio | precisa de servidor de sinalização sempre ligado (não existe na Vercel) |
| Jitsi embutido na página (`iframe`) | o meet.jit.si gratuito corta a chamada embutida depois de 5 minutos |
| JaaS (Jitsi pago da 8x8) ou Daily.co | exigem conta, chave secreta no `.env` e, no JaaS, bibliotecas novas |
| **Jitsi em outra aba** (escolhida) | sem limite de tempo, sem conta da escola, sem biblioteca nova |

O endereço do Jitsi fica em `JITSI_SERVIDOR` no `.env` (padrão `https://meet.jit.si`). Se a
escola tiver um servidor próprio do Jitsi, só essa linha muda.

## Como funciona

1. Na tela **Videochamadas** (menu do professor e da coordenação), a pessoa escolhe quem chamar
   e, se quiser, um assunto. Na lista de **Professores** da coordenação, o botão **Chamar** já
   escolhe o professor.
2. O portal grava a chamada (model `Chamada`, em `apps/videochamadas/models.py`) e, na mesma
   transação, o convite no sino de quem foi chamado (`aviso_de_chamada`, em
   `apps/alertas/regras.py`). Ou grava os dois, ou nenhum.
3. Os dois abrem a **sala** (`/videochamadas/<número>/`) e clicam em **Entrar na chamada**,
   que abre o Jitsi em outra aba, já com o nome da pessoa e o assunto preenchidos.
4. Qualquer um dos dois clica em **Encerrar chamada**. A chamada continua no histórico.

O convite vai direto para o banco, sem a fila do Celery, porque a chamada é para agora: se o
worker estivesse parado, o aviso chegaria tarde demais. É um único registro, então a tela não
fica mais lenta.

## Quem pode o quê

| Quem | Pode |
|---|---|
| Coordenador | chamar qualquer professor **ativo** |
| Professor | chamar qualquer coordenador **ativo** |
| Aluno e ADMIN | nada: a área inteira responde **403** (`@perfil_requerido`) |
| Quem não participa da chamada | nem abre a sala: **404** (`Chamada.objects.do_usuario`) |

Coordenador com coordenador ou professor com professor não é permitido: o formulário só lista
o outro perfil, e `Chamada.clean()` confere de novo antes de gravar. Quem chama é sempre quem
está logado, nunca um campo do formulário.

## Segurança da sala

No Jitsi público, **quem conhece o nome da sala entra nela**. Por isso:

- o nome é sorteado com o módulo `secrets` (o mesmo das senhas provisórias), como
  `InstitutoSocratico-3f9a1c...` (24 letras e números): existem 2^96 nomes possíveis, então
  não dá para adivinhar;
- o nome só aparece para os dois participantes, na tela da sala;
- o nome e o assunto vão depois do `#` do endereço, a parte que o navegador não envia ao
  servidor do Jitsi.

A tela avisa para não compartilhar o endereço. Quem entra primeiro no meet.jit.si pode
precisar fazer login (Google, GitHub ou Facebook) para abrir a sala. É uma regra do serviço
público contra abuso, e quem chega depois entra direto.

## Quando a chamada está "em andamento"

Uma chamada está em andamento enquanto ninguém clica em Encerrar, até **3 horas** depois de
criada (`DURACAO_MAXIMA`). Assim uma chamada esquecida não fica "em andamento" para sempre no
histórico.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `apps/videochamadas/models.py` | model `Chamada`, sorteio da sala e link do Jitsi |
| `apps/videochamadas/forms.py` | quem pode ser chamado (`pessoas_para_chamar`) |
| `apps/videochamadas/views.py` | telas: início (nova chamada e histórico), sala e encerrar |
| `apps/alertas/regras.py` | `aviso_de_chamada`: o convite no sino |
| `apps/videochamadas/tests.py` | testes de permissão, convite, sala, link e histórico |

## Para a apresentação

- A rede do SENAI pode bloquear vídeo (como já bloqueia a porta 5432 do banco). Testem a
  chamada antes, na rede onde vão apresentar, ou usem o roteador do celular.
- Usem dois navegadores (ou uma janela anônima): um logado como `coord01`, outro como `prof01`.
