# Videochamada entre coordenação e professores

## A ideia em uma frase

O coordenador chama um professor (ou o professor chama a coordenação) com um clique, e os dois
conversam por vídeo **dentro do portal**. O vídeo vai direto de um computador ao outro, sem
passar pelo nosso servidor e sem ser gravado. O aluno não participa.

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

1. Os dois abrem a sala (`/videochamadas/<número>/`). O navegador pede permissão para a câmera e
   o microfone e manda `entrei`.
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
- As respostas de `sinal/` e `ice/` têm `Cache-Control: no-cache`: nada fica guardado no
  navegador nem em proxy.
- **Nada é gravado.** O vídeo e o áudio não passam pelo portal, e o WebRTC criptografa a
  ligação entre os dois navegadores (DTLS-SRTP). Mesmo quando passa pelo TURN, o vídeo continua
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
| `apps/videochamadas/models.py` | models `Chamada` (histórico) e `SinalChamada` (recados da sinalização) |
| `apps/videochamadas/forms.py` | quem pode ser chamado (`pessoas_para_chamar`) |
| `apps/videochamadas/views.py` | telas (início, sala, encerrar) e as rotas `sinal/` e `ice/` |
| `apps/videochamadas/templates/videochamadas/_sala_propria.html` | a sala dentro do portal |
| `static/js/chamada.js` | a negociação WebRTC, os estados da conexão e os avisos |
| `apps/alertas/regras.py` | `aviso_de_chamada`: o convite no sino |
| `apps/videochamadas/tests.py` | testes de permissão, sinais, STUN/TURN, sala e histórico |

## Para a apresentação

**Resumo da fase 1 (sala própria).** Trocamos o Jitsi por uma sala de vídeo feita por nós,
dentro do portal. O vídeo vai direto entre os dois navegadores com WebRTC, que já vem no
navegador, então não instalamos nenhuma biblioteca. O Django só faz a sinalização: guarda numa
tabela os recados que os navegadores trocam para se encontrar, e cada navegador pergunta a cada
segundo se chegou algo novo. Usamos perguntas repetidas (polling) e não WebSocket porque a
Vercel desliga o sistema entre um pedido e outro. Só os dois participantes leem os recados da
chamada, o vídeo não passa pelo servidor e nada é gravado. Se a conexão direta falhar, um
servidor TURN gratuito repassa o vídeo, e o Jitsi continua como plano B.

- Testem antes, na rede onde vão apresentar. Com cada computador num celular diferente,
  configurem o TURN.
- No mesmo computador, usem uma janela normal (`coord01`) e uma anônima (`prof01`) e abaixem o
  volume de uma delas (ou usem fone): com o microfone e o alto-falante juntos, o som "apita".
- `chrome://webrtc-internals` mostra, ao vivo, a conexão e o caminho que o vídeo está fazendo.
