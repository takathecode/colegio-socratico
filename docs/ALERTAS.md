# Alertas automáticos (Celery + Redis)

## A ideia em uma frase

O sistema avisa sozinho quem precisa agir: o aluno com frequência ou média em risco, o
professor com justificativas paradas e a coordenação quando o modelo preditivo aponta risco
alto de evasão. O aviso aparece no sino do portal e, nos casos em risco, também por e-mail.

## Por que Celery e Redis

Algumas tarefas não devem travar a tela: mandar e-mail depende de outro servidor, e
recalcular o risco de todos os alunos leva tempo. Com o Celery, a tela só deixa um
**pedido na fila** e responde na hora. Um processo separado faz o trabalho depois.

| Peça | Papel | Onde está |
|---|---|---|
| **Redis** | A fila: guarda os pedidos de tarefa | Docker local ou Upstash |
| **Worker** | Pega os pedidos da fila e executa | `celery -A config worker --pool=solo -l info` |
| **Beat** | Despertador: põe a rotina diária na fila às 6h | `celery -A config beat -l info` |
| **Tarefas** | O trabalho em si | `apps/alertas/tasks.py` |
| **Regras** | Quem recebe qual alerta | `apps/alertas/regras.py` |

## As regras

| Quando | Quem recebe | Gravidade | E-mail |
|---|---|---|---|
| Frequência global abaixo de 75% | aluno | Em risco | sim |
| Média abaixo de 6 | aluno | Em risco | sim |
| Risco de evasão alto (60% ou mais) | coordenadores ativos | Em risco | sim |
| Justificativa sem resposta há mais de 3 dias | professor da disciplina | Em atenção | não |
| Professor publicou notas | aluno | Informativo | não |
| Professor aprovou ou rejeitou a justificativa | aluno | Informativo / Em atenção | não |
| Chegou uma mensagem nova | quem recebeu | Informativo | não |
| Convite para videochamada | quem foi chamado | Informativo | não |

As quatro primeiras rodam na **rotina diária** (6h). As quatro últimas são **avisos na hora**:
a tela põe a tarefa na fila logo depois de salvar ou enviar (`transaction.on_commit`). A exceção
é o convite de videochamada, gravado na mesma transação da chamada, sem a fila, porque a chamada
é para agora (ver [VIDEOCHAMADA.md](VIDEOCHAMADA.md)).

**Mensagens:** há um aviso por conversa, e não um por mensagem. Se a pessoa ainda não leu o
aviso anterior, as mensagens novas entram na mesma conversa e o sino não enche. Quando ela abre
a conversa, o aviso é marcado como lido, e a próxima mensagem avisa de novo.

Os limites são os mesmos do selo de situação (`apps/academico/calculos.py`), então o alerta
concorda com o que as outras telas mostram.

**Sem excesso:** cada alerta tem uma "chave do assunto" (ex.: `frequencia-12`). A mesma pessoa
não recebe outro alerta com a mesma chave antes de 7 dias. Sem isso, o aluno com frequência
baixa receberia o mesmo aviso todos os dias.

## E se o Redis estiver fora do ar?

`apps/alertas/fila.py` tenta colocar a tarefa na fila. Se o Redis não responder em cerca de
2 segundos, a tarefa roda ali mesmo, sem fila, e o problema fica registrado no log. O professor
nunca vê uma página de erro só porque a fila caiu.

Para usar o sistema em um computador sem Redis, coloque `CELERY_SEM_REDIS=True` no `.env`:
as tarefas rodam na hora, sem esperar. Nesse modo a rotina das 6h não acontece; use o botão
**Rodar rotina agora** na Central de alertas ou o comando `python manage.py gerar_alertas`.

O e-mail que falha é tentado de novo pelo worker até 3 vezes, com 1 minuto entre as tentativas.

## Como rodar com Redis

1. Um Redis:
   - **Docker:** `docker run -d -p 6379:6379 redis` e, no `.env`, `REDIS_URL=redis://localhost:6379/0`.
   - **Upstash** (gratuito, na nuvem): crie um banco em upstash.com e copie a URL `rediss://...`
     para o `REDIS_URL`. O `settings.py` acrescenta sozinho o `ssl_cert_reqs` que o Celery exige.
2. `CELERY_SEM_REDIS=False` no `.env`.
3. Três terminais: `python manage.py runserver`, o worker e o beat (comandos na tabela acima).

## Onde ver na demonstração

- **Sino** no topo de qualquer tela: contador de não lidos e os últimos avisos.
- **Notificações** (`/alertas/`): todos os avisos da pessoa, com o filtro "Não lidas".
- **Central de alertas** (coordenação): tudo o que o sistema enviou, com filtros, indicadores
  da semana e o botão **Rodar rotina agora**.
- Em desenvolvimento os e-mails aparecem no terminal do worker (ou do runserver, sem Redis).

Roteiro curto: entre como professor e publique uma nota. Entre como o aluno e o sino mostra
"Nota publicada". Entre como coordenador e clique em **Rodar rotina agora**: aparecem os
alertas de frequência, média e evasão, e os e-mails aparecem no terminal.
