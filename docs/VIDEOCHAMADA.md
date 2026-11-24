# Videochamada entre coordenação e professores

## A ideia em uma frase

O coordenador chama um professor (ou o professor chama a coordenação) com um clique, e os dois
conversam por vídeo **dentro do portal**. O vídeo vai direto de um computador ao outro, sem
passar pelo nosso servidor e sem ser gravado. O aluno não participa.

Quem é chamado vê, em qualquer tela do portal, a janela **"Fulano está te chamando"**, com
**Atender** e **Recusar**. O histórico mostra se cada chamada foi atendida, recusada ou não
atendida, e quanto tempo durou.

## Como funciona (sala própria, o padrão)

O vídeo usa o **WebRTC**, um recurso que todo navegador moderno já tem: dois navegadores
conseguem trocar vídeo e áudio direto, um com o outro. O problema é o começo: para se
encontrarem, os dois precisam antes trocar alguns recados. Isso se chama **sinalização**, e é a
única parte que passa pelo portal.

```
 Coordenador (navegador)            Portal (Django + Supabase)          Professor (navegador)
         |  POST sinal/ "entrei"  ──────────►  grava na tabela                    |
         |                                     SinalChamada  ◄──── GET sinal/ (a cada 1 s)
         |  GET sinal/ (a cada 1 s) ◄──────    "entrei", "oferta",                 |
         |                                     "resposta", "candidato"            |
         |                                                                         |
         |◄═════════════ vídeo e áudio direto (WebRTC), sem passar pelo portal ═══►|
```

Os recados (model `SinalChamada`, em `apps/videochamadas/models.py`) são de cinco tipos:

| Tipo | Quem manda | O que diz |
|---|---|---|
| `entrei` | os dois | "abri a sala" |
| `oferta` | quem criou a chamada | o que ele vai enviar (formatos de vídeo e áudio) |
| `resposta` | o convidado | "aceito a oferta", e o que ele vai enviar |
| `candidato` | os dois | endereços de rede onde ele pode ser encontrado |
| `saiu` | os dois | "fechei a sala" |

Passo a passo:

1. Os dois abrem a sala (`/videochamadas/<número>/`) e passam pela **pré-sala** (ver abaixo). Ao
   clicar em **Entrar na sala**, o navegador manda `entrei`.
2. Quando quem criou a chamada vê o `entrei` do outro, ele manda a `oferta`. A regra é fixa
   (sempre quem criou oferece) para os dois não oferecerem ao mesmo tempo.
3. O convidado lê a oferta e manda a `resposta`.
4. Os dois trocam `candidato`s. Os navegadores testam os endereços e ligam o vídeo direto.
5. A tela mostra **Conectado**. A partir daí, cada um só pergunta ao portal a cada 5 s, para
   perceber se o outro saiu ou se a chamada foi encerrada.

Detalhes que fazem a conexão não falhar:

- **Ordem dos recados.** Cada navegador manda um recado de cada vez, e cada um lê os recados na
  ordem em que foram gravados. Um candidato que chegue antes da oferta (ou da resposta) é
  guardado e aplicado depois.
- **Abas recarregadas.** Cada aba aberta sorteia um número (a "sessão"), e todo recado leva esse
  número. Recado de uma aba que já foi fechada é ignorado, e a sala nova começa a ler depois do
  último recado que já existia.
- **Candidatos juntos.** Os endereços de rede costumam aparecer vários de uma vez. O navegador
  espera 200 ms e manda todos num recado só, o que diminui os pedidos ao banco.
- **Sem câmera ou sem permissão.** A pessoa entra mesmo assim: vê e ouve o outro, e a tela
  explica o problema (permissão negada, câmera usada por outro programa, computador sem câmera,
  página sem HTTPS). Sem câmera, ela entra só com o microfone.

## Antes de entrar: a pré-sala

Ao abrir a sala, a pessoa ainda não está na chamada. O navegador pede permissão para a câmera e o
microfone e mostra:

- a **prévia da câmera** (espelhada, como num espelho);
- a lista de **câmeras** e de **microfones** do computador (`enumerateDevices`), para escolher
  outro aparelho (um fone de ouvido, uma câmera USB). A escolha fica guardada **neste navegador**
  (`localStorage`) e vale para as próximas chamadas. Se o aparelho guardado for desconectado, o
  navegador usa outro;
- uma **barra verde** que acompanha o volume do microfone (Web Audio, `AnalyserNode`): se ela
  mexe quando a pessoa fala, o microfone está ouvindo;
- os botões de **microfone** e **câmera**: dá para entrar com a câmera desligada.

Só ao clicar em **Entrar na sala** o outro fica sabendo que a pessoa está ali. Enquanto isso, o
portal já busca os servidores STUN/TURN, para a entrada ser rápida. Plugar ou tirar um aparelho
atualiza a lista sozinho.

## Na sala: botões e conversa

Depois de conectados, os dois navegadores abrem também um **canal de dados**
(`RTCDataChannel`), que faz parte do WebRTC. Ele vai direto entre os dois, como o vídeo. Por ele
passam:

- **a conversa (chat)**: as mensagens não passam pelo portal, não ficam no banco e somem quando
  a pessoa sai ou recarrega a sala. O campo só libera quando o outro está conectado. O texto do
  outro é mostrado com `textContent` (nunca `innerHTML`), então um `<b>` aparece como texto e
  não vira código. Limite de 500 caracteres por mensagem;
- **o estado de cada um**: "meu microfone está desligado", "minha câmera está desligada",
  "estou compartilhando a tela". A tela do outro mostra um selo ou a foto no lugar do vídeo.

Os botões ficam sobre o vídeo:

| Botão | O que faz |
|---|---|
| Microfone | desliga e religa o microfone (`track.enabled`): a ligação continua, mas vai silêncio |
| Câmera | desliga e religa a câmera; o outro vê a sua foto no lugar do vídeo |
| Compartilhar a tela | o navegador pergunta o que mostrar (a tela inteira, uma janela ou uma aba) e a imagem da tela entra no lugar da câmera; para parar, o mesmo botão ou o "Parar de compartilhar" do navegador. Não aparece no celular, que não compartilha a tela |
| Tela cheia | o vídeo ocupa a tela toda (Esc sai). Na tela cheia, mensagem nova da conversa aparece por alguns segundos sobre o vídeo |

Trocar a câmera pela tela usa `replaceTrack`: a imagem muda sem negociar a ligação de novo. Por
isso quem cria a chamada sempre abre um "canal" de áudio e um de vídeo de ida e volta, mesmo sem
câmera: um computador de laboratório sem câmera também consegue compartilhar a tela.

## Reconexão automática

Se a internet oscilar, a ligação fica "desconectada". O navegador ainda tenta voltar sozinho por
3 segundos. Se não voltar, **quem criou a chamada refaz a negociação de rede** (*ICE restart*):
manda uma oferta nova pela sinalização, o convidado responde, e os dois procuram de novo um
caminho pela rede. A ligação é a mesma, então o vídeo, a conversa e o compartilhamento de tela
continuam de onde estavam. São até 3 tentativas, com 10 segundos entre elas (e uma na hora,
quando o computador avisa que a internet voltou). Se depois de 35 segundos ainda não tiver
voltado, a tela explica o problema e sugere recarregar ou usar o Jitsi.

Só quem criou a chamada refaz a oferta (a mesma regra do começo), para os dois não fazerem ao
mesmo tempo. Cada oferta leva um número, e a resposta repete esse número: resposta de uma
oferta antiga é ignorada.

## Chamada recebida, situações e Alunos em risco

### A janela "Fulano está te chamando"

Em **qualquer tela** do professor e da coordenação, o `static/js/portal.js` pergunta ao portal a
cada 10 segundos (30 s com a aba em segundo plano, e na hora quando a pessoa volta para a aba) se
alguém está chamando: rota `GET /videochamadas/recebida/`. É polling, pelo mesmo motivo da
sinalização (ver abaixo). A resposta traz a chamada mais recente que é para a pessoa, ainda não
foi atendida, recusada nem encerrada, e começou há menos de **2 minutos** (`TEMPO_DE_TOQUE`). São
3 consultas ao banco por pergunta (2 do login e 1 da chamada).

Se houver uma, abre a janela (`templates/componentes/chamada_recebida.html`) com a foto, o nome e
o assunto de quem chama. O título da aba pisca ("Chamada de Fulano") e o navegador toca um bipe
curto feito pelo próprio Web Audio, sem arquivo de som. Se o navegador bloquear o som antes de a
pessoa clicar na página, fica só a janela.

| Botão | O que faz |
|---|---|
| **Atender** | abre a sala (e a pré-sala) |
| **Recusar** | `POST /videochamadas/<número>/recusar/` por `fetch`, sem recarregar a página (a pessoa pode estar no meio das notas); a chamada fica "Recusada" e é encerrada para os dois |
| **Esc** | fecha a janela sem recusar; ela não abre de novo naquela aba, e o convite continua no sino |

Quem chamou, esperando na sala, vê "Chamando Fulano...", depois "Fulano abriu o convite" ou
"Fulano não atendeu" (a rota `sinal/` também devolve a situação). Se a chamada for recusada, a
sala recarrega e mostra "Fulano recusou a chamada.".

### Situações no histórico

Nada novo é digitado: a situação vem de duas datas novas da `Chamada`, `atendida_em` e
`recusada_em` (migração `videochamadas/0003`), junto com `criada_em` e `encerrada_em`.

| Situação | Quando |
|---|---|
| Chamando | ninguém atendeu ainda e faz menos de 2 minutos |
| Em andamento | o convidado abriu a sala, e a chamada não acabou |
| Atendida | o convidado abriu a sala, e a chamada acabou |
| Recusada | o convidado clicou em Recusar |
| Não atendida | passaram 2 minutos (ou quem chamou desistiu) sem o convidado abrir a sala |

**Atendida = o convidado abriu a sala** (pelo botão Atender, pelo sino ou pelo histórico). A
regra vale igual no modo `proprio` e no `jitsi`. Se ele abrir a sala depois dos 2 minutos, com
quem chamou ainda esperando, a chamada ainda vira "Em andamento".

A **duração** vai do atendimento ao encerramento ("menos de 1 min", "12 min", "1 h 05 min"). Uma
chamada que ninguém encerrou (as duas abas fechadas) não tem duração no histórico: não dá para
saber quando a conversa acabou.

### "Chamar professor sobre este aluno"

Na tela **Alunos em risco** da coordenação, cada aluno tem o menu **Chamar professor**, que lista
só os **professores ativos das disciplinas da turma do aluno**, com as disciplinas de cada um. A
lista sai de uma consulta só para a página inteira (`marcar_professores_para_chamar`, em
`apps/coordenacao/views.py`). Escolher um professor abre Videochamadas com o professor e o
assunto já preenchidos ("Aluno em risco: Nome (RA ...)"), pelos parâmetros `?para=` e
`?assunto=`. A chamada só sai quando o coordenador confere e clica em **Chamar agora**: o
formulário valida tudo de novo, como em qualquer chamada.

## Por que a sinalização é por polling (e não por WebSocket)

O jeito mais comum de fazer sinalização é um **WebSocket**: uma conexão que fica aberta e o
servidor "empurra" o recado na hora. Só que o sistema vai para a **Vercel**, que é *serverless*:
cada pedido roda numa cópia do sistema que é desligada logo depois. Lá não existe um servidor
sempre ligado para segurar conexões abertas.

Por isso cada navegador **pergunta** ao portal se chegou algo novo (*polling*): a cada 1 s
enquanto conecta e a cada 5 s depois de conectado. São pedidos HTTP comuns, que funcionam igual
no `runserver`, na Vercel e em qualquer rede, sem biblioteca nova. O custo é pequeno porque a
sinalização só dura alguns segundos: o vídeo, que é o pesado, não passa pelo portal.

| Opção | Por que não escolhemos |
|---|---|
| WebSocket (Django Channels, Daphne) | biblioteca nova e servidor sempre ligado, que a Vercel não tem |
| Serviço pago (LiveKit, Daily.co, JaaS) | conta, chave secreta e biblioteca nova; o vídeo passa pelo servidor deles |
| Jitsi embutido na página (`iframe`) | o meet.jit.si gratuito corta a chamada embutida depois de 5 minutos |
| Jitsi em outra aba | funciona, mas sai do portal e pode exigir login no Jitsi; virou o **plano B** |
| **WebRTC + sinalização por polling** (escolhida) | dentro do portal, gratuito, sem biblioteca nova, funciona na Vercel |

## Encontrar o outro computador: STUN e TURN

Os dois computadores quase sempre estão atrás de um roteador, sem endereço público. Para se
acharem, o navegador usa:

- **STUN** (sempre ligado): um servidor público da Cloudflare (`stun.cloudflare.com`) que só diz
  a cada navegador qual é o seu endereço na internet. Não recebe o vídeo e não tem senha.
- **TURN** (opcional, no `.env`): quando a ligação direta é impossível, o vídeo passa por esse
  servidor, que só o retransmite. Isso acontece muito quando **cada computador está no roteador
  de um celular diferente**, porque as operadoras escondem vários clientes atrás de um mesmo
  endereço. Também ajuda em redes que bloqueiam o tráfego de vídeo (o TURN pode usar a porta
  443, a mesma dos sites).

A lista de servidores vem da rota `ice/`, que só responde a quem participa da chamada. Sem as
variáveis do TURN, a lista tem só o STUN.

### Como criar o TURN gratuito (Metered / Open Relay)

1. Abra **https://www.metered.ca/stun-turn** e crie uma conta gratuita (plano "Free").
2. No painel, crie um app (o nome vira um endereço como `institutosocratico.metered.live`).
3. Abra **TURN Server** e crie uma credencial (botão como **Add Credential**). O painel mostra
   um **Username**, uma **Password** (ou *Credential*) e a lista de endereços (`turn:` e `turns:`).
4. No `.env` (nunca no código nem no `.env.example`), preencha:

   ```
   TURN_URLS=turn:global.relay.metered.ca:80,turn:global.relay.metered.ca:80?transport=tcp,turn:global.relay.metered.ca:443,turns:global.relay.metered.ca:443?transport=tcp
   TURN_USUARIO=o Username do painel
   TURN_SENHA=a Password do painel
   ```

   Copie os endereços que o **seu** painel mostrar, separados por vírgula e sem espaços (os de
   cima são o formato usual). As linhas `stun:` do painel podem ficar de fora: o portal já
   usa o STUN da Cloudflare.
5. Reinicie o `runserver`. Na Vercel, as mesmas três variáveis entram em *Settings >
   Environment Variables* (etapa 14).
6. Para conferir: numa chamada conectada, abra `chrome://webrtc-internals` em outra aba. Se a
   linha do par de candidatos escolhido mostrar `relay`, o vídeo está passando pelo TURN.

O plano gratuito tem um limite de tráfego por mês (o valor aparece no painel). O TURN só é usado
quando a ligação direta falha, e uma hora de chamada passando por ele gasta perto de 1 GB.

O navegador precisa da senha do TURN para usá-lo, então quem participa de uma chamada consegue
vê-la nas ferramentas do navegador. Isso vale para qualquer sistema com TURN de senha fixa. Por
isso ela só chega a quem participa de uma chamada em andamento, e no painel do Metered dá para
trocar a credencial a qualquer momento.

## Plano B: Jitsi Meet

`VIDEO_MODO` no `.env`:

| Valor | O que acontece |
|---|---|
| `proprio` (padrão) | sala dentro do portal (WebRTC) |
| `jitsi` | a sala mostra o botão **Entrar na chamada**, que abre o Jitsi Meet em outra aba; as rotas `sinal/` e `ice/` respondem 404 |

Mesmo no modo `proprio`, a sala tem o link discreto **"Não conectou? Entrar pelo Jitsi"**: os
dois clicam e continuam a conversa no Jitsi. Ao clicar, a sala própria desliga para não usar a
câmera duas vezes. O endereço do Jitsi fica em `JITSI_SERVIDOR` (padrão `https://meet.jit.si`).
O nome da sala no Jitsi é sorteado com o módulo `secrets` (2^96 possibilidades), porque no
Jitsi público quem conhece o nome entra na sala. Por isso a tela pede para não compartilhar o
link.

## Quem pode o quê

| Quem | Pode |
|---|---|
| Coordenador | chamar qualquer professor **ativo** |
| Professor | chamar qualquer coordenador **ativo** |
| Aluno e ADMIN | nada: a área inteira responde **403** (`@perfil_requerido`) |
| Quem não participa da chamada | nem abre a sala, nem lê ou manda sinais: **404** (`Chamada.objects.do_usuario`) |
| Convidado | recusar a chamada (quem chamou recebe **404** em `recusar/`; chamada já atendida ou encerrada dá **400**) |

Coordenador com coordenador ou professor com professor não é permitido: o formulário só lista
o outro perfil, e `Chamada.clean()` confere de novo antes de gravar. Quem chama é sempre quem
está logado, nunca um campo do formulário.

## Segurança da sinalização

- `sinal/` e `ice/` usam `@login_required` + `@perfil_requerido("PROFESSOR", "COORDENADOR")` e
  buscam a chamada por `Chamada.objects.do_usuario`: quem não participa recebe 404.
- **Cada pessoa só lê os recados destinados a ela** (`para = quem pergunta`), na chamada de que
  participa. O destinatário de um recado é sempre o outro participante, calculado pelo servidor
  (o navegador não escolhe para quem manda).
- Os POSTs levam o token CSRF no cabeçalho `X-CSRFToken`. Nenhuma view usa `csrf_exempt`.
- O portal recusa com **400**: chamada encerrada (ou com mais de 3 horas), tipo fora da lista,
  conteúdo que não é um objeto JSON e recado com mais de **16 KB** (uma oferta de vídeo e áudio tem cerca de 6 KB).
- Os recados são apagados quando a chamada é encerrada, e os com mais de **2 horas** são
  apagados sempre que alguém entra numa sala (sem Celery).
- `recebida/` só devolve chamadas **para quem pergunta**, e `recusar/` só aceita o convidado
  (POST com o token CSRF no cabeçalho). O nome e o assunto aparecem na janela com
  `textContent`, nunca como HTML.
- As respostas de `sinal/`, `ice/` e `recebida/` têm `Cache-Control: no-cache`: nada fica guardado no
  navegador nem em proxy.
- **Nada é gravado.** O vídeo, o áudio e a conversa não passam pelo portal, e o WebRTC
  criptografa a ligação entre os dois navegadores (DTLS-SRTP no vídeo, DTLS no canal de dados). Mesmo quando passa pelo TURN, o vídeo continua
  criptografado: o TURN só repassa os pacotes.
- A câmera só funciona em página segura: `https://` ou `http://localhost`. No servidor
  publicado, `USAR_HTTPS=True` (ver [SEGURANCA.md](SEGURANCA.md)).

## Quando a chamada está "em andamento"

Uma chamada está em andamento enquanto ninguém clica em **Encerrar para os dois**, até
**3 horas** depois de criada (`DURACAO_MAXIMA`). **Sair da chamada** só fecha a sala para quem
clicou: o outro vê "Aguardando o outro entrar..." e a pessoa pode voltar. Quando a chamada é
encerrada, a tela do outro percebe em até 5 s e mostra "Esta chamada foi encerrada".

## Arquivos

| Arquivo | O que faz |
|---|---|
| `apps/videochamadas/models.py` | models `Chamada` (histórico, situação e duração) e `SinalChamada` (recados da sinalização) |
| `apps/videochamadas/forms.py` | quem pode ser chamado (`pessoas_para_chamar`) |
| `apps/videochamadas/views.py` | telas (início, sala, encerrar), as rotas `sinal/` e `ice/` e as rotas `recebida/` e `recusar/` |
| `apps/videochamadas/templates/videochamadas/_sala_propria.html` | a sala dentro do portal |
| `static/js/chamada.js` | a pré-sala, a negociação WebRTC, os botões, a conversa, a reconexão, os estados da conexão e os avisos |
| `templates/componentes/chamada_recebida.html` + `static/js/portal.js` | a janela "Fulano está te chamando" |
| `apps/coordenacao/templates/coordenacao/_chamar_professor.html` | o menu "Chamar professor" de Alunos em risco |
| `apps/alertas/regras.py` | `aviso_de_chamada`: o convite no sino |
| `apps/videochamadas/tests.py` | testes de permissão, sinais, STUN/TURN, sala, histórico, situações, chamada recebida e Alunos em risco |

## Para a apresentação

**Resumo da fase 1 (sala própria).** Trocamos o Jitsi por uma sala de vídeo feita por nós,
dentro do portal. O vídeo vai direto entre os dois navegadores com WebRTC, que já vem no
navegador, então não instalamos nenhuma biblioteca. O Django só faz a sinalização: guarda numa
tabela os recados que os navegadores trocam para se encontrar, e cada navegador pergunta a cada
segundo se chegou algo novo. Usamos perguntas repetidas (polling) e não WebSocket porque a
Vercel desliga o sistema entre um pedido e outro. Só os dois participantes leem os recados da
chamada, o vídeo não passa pelo servidor e nada é gravado. Se a conexão direta falhar, um
servidor TURN gratuito repassa o vídeo, e o Jitsi continua como plano B.

**Resumo da fase 2 (botões, conversa e reconexão).** Na sala dá para desligar o microfone e a
câmera, compartilhar a tela e usar a tela cheia. A conversa e os avisos de "microfone
desligado" vão por um canal de dados do próprio WebRTC, direto entre os navegadores: o portal
não vê as mensagens e nada fica no banco. Se a internet oscilar, quem criou a chamada refaz a
negociação de rede sozinho, sem fechar a ligação, e a conversa continua.

**Resumo da fase 3 (integração com o portal).** Agora a chamada "toca": em qualquer tela, o
professor vê a janela "Fulano está te chamando", com Atender e Recusar, e a aba pisca e apita. O
navegador pergunta ao portal a cada 10 segundos, pelo mesmo motivo do polling da sinalização. O
histórico mostra se a chamada foi atendida, recusada ou não atendida, e quanto durou, tudo
calculado por datas guardadas na chamada. Antes de entrar, cada um passa por uma pré-sala, vê a
própria câmera, escolhe o microfone e confere se ele está ouvindo. E na tela de Alunos em risco,
a coordenação chama o professor de uma disciplina do aluno com o assunto já preenchido: o modelo
de evasão aponta o aluno, e a conversa com o professor começa em dois cliques.

- Testem antes, na rede onde vão apresentar. Com cada computador num celular diferente,
  configurem o TURN.
- No mesmo computador, usem uma janela normal (`coord01`) e uma anônima (`prof01`) e abaixem o
  volume de uma delas (ou usem fone): com o microfone e o alto-falante juntos, o som "apita".
- `chrome://webrtc-internals` mostra, ao vivo, a conexão e o caminho que o vídeo está fazendo.
