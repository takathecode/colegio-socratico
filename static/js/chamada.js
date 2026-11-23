// Sala de vídeo própria (videochamadas/_sala_propria.html). JavaScript puro, sem biblioteca.
//
// O vídeo, o áudio e a conversa vão DIRETO de um navegador ao outro (WebRTC): não passam pelo
// portal e não são gravados. O portal só leva os "sinais", recados curtos que os dois
// navegadores trocam para se encontrar:
//   entrei    → "abri a sala"
//   oferta    → quem criou a chamada descreve o que vai enviar (formato do vídeo, do áudio...)
//   resposta  → o convidado aceita a oferta e descreve o que ele vai enviar
//   candidato → endereços de rede onde o navegador pode ser encontrado (vários por sinal)
//   saiu      → "fechei a sala"
// Os sinais são enviados por POST e lidos por GET a cada 1 s enquanto conecta (polling), e a
// cada 5 s depois de conectado, só para perceber se o outro saiu ou se a chamada foi encerrada.
//
// Cada aba aberta tem um número sorteado (sessão). Todo sinal diz de qual aba veio e, quando
// é uma resposta a alguém, para qual aba vai. Assim um recado de uma aba que já foi fechada
// (ou recarregada) nunca atrapalha a conversa da aba nova.
//
// Depois de conectados, os dois navegadores também abrem um "canal de dados" (RTCDataChannel)
// direto entre eles. Por ele passam as mensagens da conversa e o aviso "desliguei o microfone"
// ou "estou compartilhando a tela". Nada disso passa pelo portal.
//
// Se a internet oscilar e a ligação cair, quem criou a chamada refaz a negociação de rede
// ("ICE restart") sem fechar a ligação: o vídeo e a conversa voltam sozinhos.

(() => {
  const sala = document.querySelector("[data-sala-propria]");
  if (!sala) {
    return;
  }

  // --- Configuração vinda do template ---
  const URL_SINAL = sala.dataset.urlSinal;
  const URL_ICE = sala.dataset.urlIce;
  const URL_INICIO = sala.dataset.urlInicio;
  const NOME_DO_OUTRO = sala.dataset.nomeDoOutro;
  const SOU_QUEM_CHAMOU = sala.dataset.souQuemChamou === "true";
  const TOKEN_CSRF = sala.querySelector("[name=csrfmiddlewaretoken]").value;

  const INTERVALO_CONECTANDO = 1000; // ms entre as consultas enquanto conecta
  const INTERVALO_CONECTADO = 5000; // depois de conectado, só para perceber "saiu"/"encerrada"
  const INTERVALO_SEM_REDE = 3000; // o portal não respondeu: tenta de novo com calma
  const ESPERA_DOS_CANDIDATOS = 200; // junta os candidatos que aparecem nesse intervalo

  // Reconexão automática
  const ESPERA_ANTES_DE_RECONECTAR = 3000; // "Reconectando..." por 3 s: refaz a negociação
  const INTERVALO_ENTRE_TENTATIVAS = 10000; // cada tentativa espera 10 s antes da próxima
  const TENTATIVAS_DE_RECONEXAO = 3;
  const ESPERA_PARA_AVISAR_A_FALHA = 35000; // depois disso, explica o problema na tela

  // Conversa
  const LIMITE_DA_MENSAGEM = 500; // caracteres (o mesmo maxlength do campo)
  const LIMITE_DO_RECADO = 4096; // recado maior que isso pelo canal de dados é ignorado
  const TEMPO_DO_RECADO_NA_TELA_CHEIA = 6000;

  // --- Elementos da tela ---
  const palco = sala.querySelector("[data-palco]");
  const videoRemoto = sala.querySelector("[data-video-remoto]");
  const videoLocal = sala.querySelector("[data-video-local]");
  const semCamera = sala.querySelector("[data-sem-camera]");
  const capa = sala.querySelector("[data-capa]");
  const capaTexto = sala.querySelector("[data-capa-texto]");
  const textoEstado = sala.querySelector("[data-estado-conexao]");
  const luz = sala.querySelector("[data-luz]");
  const aviso = sala.querySelector("[data-aviso]");
  const avisoTexto = sala.querySelector("[data-aviso-texto]");
  const botaoSom = sala.querySelector("[data-ativar-som]");
  const outroSemVideo = sala.querySelector("[data-outro-sem-video]");
  const outroMudo = sala.querySelector("[data-outro-mudo]");
  const outroTela = sala.querySelector("[data-outro-tela]");
  const recadoNaTelaCheia = sala.querySelector("[data-recado]");
  const botaoMicrofone = sala.querySelector("[data-botao-microfone]");
  const botaoCamera = sala.querySelector("[data-botao-camera]");
  const botaoTela = sala.querySelector("[data-botao-tela]");
  const botaoTelaCheia = sala.querySelector("[data-botao-tela-cheia]");
  const listaDaConversa = sala.querySelector("[data-conversa]");
  const formConversa = sala.querySelector("[data-form-conversa]");
  const campoConversa = sala.querySelector("[data-campo-conversa]");
  const botaoEnviar = sala.querySelector("[data-enviar-conversa]");

  // --- Situação da sala ---
  const minhaSessao = sortearSessao();
  let ultimoSinal = Number(sala.dataset.ultimoSinal) || 0; // último sinal já lido
  let conexao = null; // RTCPeerConnection: a ligação direta com o outro navegador
  let canal = null; // RTCDataChannel: a conversa e os avisos de microfone/câmera
  let midiaLocal = null; // câmera e microfone (ou null, se não deu para usar)
  let telaCompartilhada = null; // MediaStream da tela, enquanto estiver compartilhando
  let enviadores = { audio: null, video: null }; // por onde sai cada faixa (RTCRtpSender)
  let videoDoOutro = null; // MediaStream com o que chega do outro
  let estadoDoOutro = { microfone: true, video: true, tela: false };
  let sessaoDoOutro = null; // aba do outro com quem estamos conversando
  let candidatosPendentes = []; // candidatos que chegaram antes da oferta/resposta
  let filaDeEnvio = Promise.resolve(); // os sinais saem um de cada vez, na ordem
  let conectado = false;
  let jaConectou = false; // esta ligação já mostrou vídeo? (a reconexão não cobre a tela)
  let ativa = true; // false depois de sair ou de a chamada acabar
  let servidoresIce = [];
  let proximaConsulta = null;
  let numeroDaOferta = 0; // cada oferta tem um número; a resposta repete o número
  let tentativasDeReconexao = 0;
  let relogioDaReconexao = null;
  let relogioDaFalha = null;

  function sortearSessao() {
    // crypto.getRandomValues funciona mesmo fora do HTTPS (o randomUUID, não).
    const numeros = crypto.getRandomValues(new Uint8Array(8));
    return Array.from(numeros, (n) => n.toString(16).padStart(2, "0")).join("");
  }

  function pausa(milissegundos) {
    return new Promise((pronto) => setTimeout(pronto, milissegundos));
  }

  function mostrarSe(elemento, mostrar) {
    elemento.classList.toggle("hidden", !mostrar);
    elemento.classList.toggle("flex", mostrar);
  }

  // --- Tela: estado da conexão, capa e avisos ---
  const CORES_DA_LUZ = {
    esperando: "bg-amber-500",
    conectado: "bg-green-500",
    problema: "bg-red-500",
  };

  function mostrarEstado(texto, { cor = "esperando", mostrarCapa = true, textoDaCapa = texto } = {}) {
    textoEstado.textContent = texto;
    luz.classList.remove(...Object.values(CORES_DA_LUZ));
    luz.classList.add(CORES_DA_LUZ[cor]);
    mostrarSe(capa, mostrarCapa);
    capaTexto.textContent = textoDaCapa;
  }

  // O aviso da câmera/microfone fica guardado: ele continua valendo depois de conectar,
  // enquanto o aviso de "não conectou" some quando a conexão volta.
  let avisoDaMidia = "";

  function mostrarAviso(texto) {
    avisoTexto.textContent = texto;
    mostrarSe(aviso, Boolean(texto));
  }

  function avisarSobreAMidia(texto) {
    avisoDaMidia = texto;
    mostrarAviso(texto);
  }

  // --- Conversa com o portal (sinalização) ---
  async function postar(corpo, { keepalive = false } = {}) {
    // keepalive: o pedido continua mesmo se a página estiver fechando (sinal "saiu").
    const opcoes = {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": TOKEN_CSRF },
      body: corpo,
      credentials: "same-origin",
      keepalive,
    };
    if (keepalive) {
      return fetch(URL_SINAL, opcoes).catch(() => {});
    }
    // Se a rede falhar, tenta mais duas vezes. Um 400 (recusado) não adianta repetir.
    for (let tentativa = 1; tentativa <= 3; tentativa += 1) {
      try {
        const resposta = await fetch(URL_SINAL, opcoes);
        if (resposta.status < 500) {
          return resposta;
        }
      } catch (erro) {
        // sem rede: espera e tenta de novo
      }
      await pausa(1000);
    }
    return null;
  }

  function corpoDoSinal(tipo, conteudo = {}) {
    return JSON.stringify({ tipo, conteudo: { ...conteudo, sessao: minhaSessao } });
  }

  function enviarSinal(tipo, conteudo) {
    // Fila: cada sinal só sai depois do anterior. Assim o portal grava na mesma ordem em que
    // foram criados (a oferta sempre antes dos candidatos), e o outro lê nessa ordem.
    const corpo = corpoDoSinal(tipo, conteudo);
    filaDeEnvio = filaDeEnvio.then(() => postar(corpo)).catch(() => {});
    return filaDeEnvio;
  }

  let consultando = false;

  function consultarJa() {
    // Antecipa a próxima consulta (ex.: a ligação caiu e o outro pode ter recarregado a página).
    if (ativa && !consultando) {
      clearTimeout(proximaConsulta);
      consultar();
    }
  }

  async function consultar() {
    if (!ativa) {
      return;
    }
    consultando = true;
    let intervalo = INTERVALO_SEM_REDE;
    try {
      const resposta = await fetch(`${URL_SINAL}?depois=${ultimoSinal}`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      // Login vencido (redirecionou para a tela de login) ou sem acesso: recarrega a página,
      // e o portal mostra a tela certa.
      if (resposta.redirected || resposta.status === 403 || resposta.status === 404) {
        terminar();
        return;
      }
      if (resposta.ok) {
        const dados = await resposta.json();
        for (const sinal of dados.sinais) {
          ultimoSinal = Math.max(ultimoSinal, sinal.id);
          try {
            await tratarSinal(sinal);
          } catch (erro) {
            console.warn("Sinal não aplicado:", sinal.tipo, erro);
          }
        }
        if (dados.encerrada) {
          terminar();
          return;
        }
        intervalo = conectado ? INTERVALO_CONECTADO : INTERVALO_CONECTANDO;
      }
    } catch (erro) {
      // Portal fora do ar ou internet caiu: a próxima consulta tenta de novo.
    }
    consultando = false;
    if (ativa) {
      proximaConsulta = setTimeout(consultar, intervalo);
    }
  }

  // --- O que fazer com cada sinal recebido ---
  async function tratarSinal(sinal) {
    const conteudo = sinal.conteudo || {};
    // Recado para outra aba minha (por exemplo, uma que eu já fechei): ignora.
    if (conteudo.para_sessao && conteudo.para_sessao !== minhaSessao) {
      return;
    }
    const sessao = conteudo.sessao;
    if (!sessao) {
      return;
    }
    if (sinal.tipo === "entrei") {
      await outroEntrou(sessao);
    } else if (sinal.tipo === "oferta") {
      await receberOferta(sessao, conteudo);
    } else if (sinal.tipo === "resposta") {
      await receberResposta(sessao, conteudo);
    } else if (sinal.tipo === "candidato") {
      for (const candidato of conteudo.candidatos || []) {
        await receberCandidato(sessao, candidato);
      }
    } else if (sinal.tipo === "saiu") {
      outroSaiu(sessao);
    }
  }

  async function outroEntrou(sessao) {
    if (sessao === sessaoDoOutro) {
      return; // já estamos conversando com esta aba
    }
    sessaoDoOutro = sessao;
    fecharConexao();
    mostrarEstado("Conectando...", { textoDaCapa: "O outro participante entrou. Conectando..." });
    if (SOU_QUEM_CHAMOU) {
      // Regra fixa para os dois não fazerem oferta ao mesmo tempo: quem criou a chamada oferece.
      novaConexao();
      await enviarOferta();
    } else {
      // O convidado avisa a aba nova de quem chamou que está aqui; ela responde com a oferta.
      enviarSinal("entrei", { para_sessao: sessao });
    }
  }

  async function enviarOferta({ reiniciarRede = false } = {}) {
    // reiniciarRede (ICE restart): a ligação continua a mesma, mas os dois procuram de novo
    // o caminho pela rede. É o que traz o vídeo de volta quando a internet oscila.
    numeroDaOferta += 1;
    const oferta = await conexao.createOffer({ iceRestart: reiniciarRede });
    await conexao.setLocalDescription(oferta);
    enviarSinal("oferta", {
      para_sessao: sessaoDoOutro,
      descricao: descricaoLocal(),
      numero: numeroDaOferta,
    });
  }

  async function receberOferta(sessao, { descricao, numero }) {
    if (SOU_QUEM_CHAMOU || !descricao) {
      return; // só o convidado recebe oferta
    }
    // Oferta da mesma aba numa ligação que já existe: é a reconexão (ICE restart).
    const reconexao = Boolean(conexao && sessao === sessaoDoOutro && conexao.remoteDescription);
    if (sessao !== sessaoDoOutro || !conexao) {
      sessaoDoOutro = sessao;
      novaConexao();
    }
    if (!reconexao) {
      mostrarEstado("Conectando...", { textoDaCapa: "Conectando..." });
    }
    await conexao.setRemoteDescription(descricao);
    await aplicarCandidatosPendentes();
    // O convidado põe a câmera e o microfone depois de ler a oferta, nos mesmos "canais".
    await ligarCanaisDoConvidado();
    const resposta = await conexao.createAnswer();
    await conexao.setLocalDescription(resposta);
    enviarSinal("resposta", { para_sessao: sessao, descricao: descricaoLocal(), numero });
    // Na reconexão, a ligação deste lado pode nem ter caído (aí o navegador não avisa nada):
    // a tela mostra o estado real, e não "Reconectando...".
    if (reconexao) {
      atualizarEstadoDaConexao();
    }
  }

  async function receberResposta(sessao, { descricao, numero }) {
    if (!SOU_QUEM_CHAMOU || !conexao || sessao !== sessaoDoOutro || !descricao) {
      return;
    }
    // Resposta repetida, atrasada ou de uma oferta antiga (já mandamos outra depois dela).
    if (conexao.signalingState !== "have-local-offer" || numero !== numeroDaOferta) {
      return;
    }
    await conexao.setRemoteDescription(descricao);
    await aplicarCandidatosPendentes();
    atualizarEstadoDaConexao(); // a ligação pode ter voltado sem o navegador avisar
  }

  async function receberCandidato(sessao, candidato) {
    if (!conexao || sessao !== sessaoDoOutro || !candidato) {
      return;
    }
    // Candidato que chegou antes da oferta/resposta ser aplicada: guarda para depois.
    if (!conexao.remoteDescription) {
      candidatosPendentes.push(candidato);
      return;
    }
    try {
      await conexao.addIceCandidate(candidato);
    } catch (erro) {
      // Candidato de antes de uma reconexão: não vale mais, e os outros continuam.
      console.warn("Candidato de rede não aplicado:", erro);
    }
  }

  async function aplicarCandidatosPendentes() {
    const pendentes = candidatosPendentes;
    candidatosPendentes = [];
    for (const candidato of pendentes) {
      try {
        await conexao.addIceCandidate(candidato);
      } catch (erro) {
        console.warn("Candidato de rede não aplicado:", erro);
      }
    }
  }

  function outroSaiu(sessao) {
    if (sessao !== sessaoDoOutro) {
      return;
    }
    sessaoDoOutro = null;
    fecharConexao();
    escreverAvisoNaConversa(`${NOME_DO_OUTRO} saiu da sala.`);
    mostrarEstado("Aguardando o outro entrar...", {
      textoDaCapa: "O outro participante saiu. Aguardando o outro entrar...",
    });
  }

  // --- A ligação direta (RTCPeerConnection) ---
  function descricaoLocal() {
    return { type: conexao.localDescription.type, sdp: conexao.localDescription.sdp };
  }

  function novaConexao() {
    fecharConexao();
    const esta = new RTCPeerConnection({ iceServers: servidoresIce });
    const paraSessao = sessaoDoOutro;
    conexao = esta;

    videoDoOutro = new MediaStream();
    videoRemoto.srcObject = videoDoOutro;

    // Os endereços de rede encontrados vão para o outro em sinais "candidato". Eles costumam
    // aparecer vários de uma vez, então esperamos 200 ms e mandamos todos num pedido só:
    // menos pedidos ao portal (e ao banco) e a conexão sai mais rápido.
    let candidatosParaEnviar = [];
    esta.onicecandidate = (evento) => {
      if (!evento.candidate || esta !== conexao) {
        return;
      }
      candidatosParaEnviar.push(evento.candidate.toJSON());
      if (candidatosParaEnviar.length === 1) {
        setTimeout(() => {
          const candidatos = candidatosParaEnviar;
          candidatosParaEnviar = [];
          if (esta === conexao) {
            enviarSinal("candidato", { para_sessao: paraSessao, candidatos });
          }
        }, ESPERA_DOS_CANDIDATOS);
      }
    };
    esta.ontrack = (evento) => {
      if (esta === conexao) {
        videoDoOutro.addTrack(evento.track);
        tocarVideoRemoto();
      }
    };
    esta.onconnectionstatechange = () => {
      if (esta === conexao) {
        atualizarEstadoDaConexao();
      }
    };
    // O convidado recebe o canal de dados que quem chamou criou.
    esta.ondatachannel = (evento) => {
      if (esta === conexao) {
        prepararCanal(evento.channel);
      }
    };

    if (SOU_QUEM_CHAMOU) {
      // Quem oferece cria um "canal" de áudio e um de vídeo, sempre de ida e volta, mesmo sem
      // câmera ou microfone. Assim dá para compartilhar a tela depois, num computador sem
      // câmera, sem negociar tudo de novo. O canal de dados também precisa existir antes da
      // oferta.
      for (const tipo of ["audio", "video"]) {
        const faixa = faixaParaEnviar(tipo);
        const transceptor = esta.addTransceiver(faixa || tipo, { direction: "sendrecv" });
        enviadores[tipo] = transceptor.sender;
      }
      prepararCanal(esta.createDataChannel("conversa"));
    }
  }

  async function ligarCanaisDoConvidado() {
    // Os canais vieram na oferta. O convidado deixa todos de ida e volta e põe neles a câmera
    // (ou a tela compartilhada) e o microfone.
    for (const transceptor of conexao.getTransceivers()) {
      const tipo = transceptor.receiver.track.kind;
      if (transceptor.currentDirection === "stopped" || !(tipo in enviadores)) {
        continue;
      }
      transceptor.direction = "sendrecv";
      enviadores[tipo] = transceptor.sender;
      const faixa = faixaParaEnviar(tipo);
      if (transceptor.sender.track !== faixa) {
        await transceptor.sender.replaceTrack(faixa);
      }
    }
  }

  function faixaParaEnviar(tipo) {
    // O vídeo enviado é a tela, enquanto ela estiver compartilhada; senão, a câmera.
    if (tipo === "video" && telaCompartilhada) {
      return telaCompartilhada.getVideoTracks()[0] || null;
    }
    return midiaLocal?.getTracks().find((faixa) => faixa.kind === tipo) || null;
  }

  function fecharConexao() {
    if (conexao) {
      conexao.close();
      conexao = null;
    }
    canal = null;
    enviadores = { audio: null, video: null };
    conectado = false;
    jaConectou = false;
    candidatosPendentes = [];
    pararReconexao();
    videoRemoto.srcObject = null;
    mostrarSe(botaoSom, false);
    estadoDoOutro = { microfone: true, video: true, tela: false };
    atualizarIndicadoresDoOutro();
    liberarConversa(false);
  }

  function atualizarEstadoDaConexao() {
    const estado = conexao.connectionState;
    if (estado === "connected") {
      conectado = true;
      jaConectou = true;
      pararReconexao();
      mostrarAviso(avisoDaMidia); // some o aviso de "não conectou"; o da câmera continua
      mostrarEstado("Conectado", { cor: "conectado", mostrarCapa: false });
    } else if (estado === "disconnected") {
      // A internet oscilou. O navegador ainda tenta voltar sozinho; se não voltar em 3 s,
      // quem chamou refaz a negociação de rede. O vídeo fica parado até lá.
      conectado = false;
      mostrarEstado("Reconectando...", { mostrarCapa: false });
      consultarJa(); // talvez o outro tenha recarregado a página: confere os sinais agora
      agendarReconexao(ESPERA_ANTES_DE_RECONECTAR);
      agendarAvisoDeFalha();
    } else if (estado === "failed") {
      conectado = false;
      consultarJa();
      mostrarEstado("Tentando conectar de novo...", {
        mostrarCapa: !jaConectou,
        textoDaCapa: "Tentando conectar de novo...",
      });
      agendarReconexao(0);
      agendarAvisoDeFalha();
    } else if (estado === "connecting") {
      mostrarEstado(jaConectou ? "Reconectando..." : "Conectando...", {
        mostrarCapa: !jaConectou,
        textoDaCapa: "Conectando...",
      });
    }
  }

  // --- Reconexão automática ---
  // Só quem criou a chamada refaz a oferta (a mesma regra do começo), para os dois não
  // fazerem ao mesmo tempo. O convidado só espera e responde.
  function agendarReconexao(espera) {
    if (!SOU_QUEM_CHAMOU || relogioDaReconexao !== null) {
      return;
    }
    relogioDaReconexao = setTimeout(reconectar, espera);
  }

  async function reconectar() {
    relogioDaReconexao = null;
    if (!ativa || !conexao || conectado || !sessaoDoOutro) {
      return;
    }
    if (tentativasDeReconexao >= TENTATIVAS_DE_RECONEXAO) {
      return; // o aviso de falha explica o que fazer
    }
    tentativasDeReconexao += 1;
    try {
      await enviarOferta({ reiniciarRede: true });
    } catch (erro) {
      console.warn("Não foi possível refazer a negociação:", erro);
    }
    // Se esta tentativa não der certo, a próxima sai depois do intervalo.
    agendarReconexao(INTERVALO_ENTRE_TENTATIVAS);
  }

  function agendarAvisoDeFalha() {
    if (relogioDaFalha === null) {
      relogioDaFalha = setTimeout(mostrarFalha, ESPERA_PARA_AVISAR_A_FALHA);
    }
  }

  function pararReconexao() {
    clearTimeout(relogioDaReconexao);
    clearTimeout(relogioDaFalha);
    relogioDaReconexao = null;
    relogioDaFalha = null;
    tentativasDeReconexao = 0;
  }

  function mostrarFalha() {
    relogioDaFalha = null;
    if (!ativa || conectado || !conexao) {
      return;
    }
    mostrarEstado("Não foi possível conectar", {
      cor: "problema",
      mostrarCapa: !jaConectou,
      textoDaCapa: "Não foi possível conectar os dois computadores.",
    });
    mostrarAviso(
      "A conexão direta entre os dois computadores não funcionou. Isso costuma acontecer " +
        "quando cada um está numa rede diferente (como dois roteadores de celular) e o " +
        "servidor TURN não está configurado, ou quando a internet de um dos dois caiu. " +
        'Recarreguem a página ou usem o link "Não conectou? Entrar pelo Jitsi", abaixo.'
    );
  }

  // A internet do computador voltou: confere os sinais e, se for quem chamou, tenta já.
  window.addEventListener("online", () => {
    consultarJa();
    if (conexao && !conectado && SOU_QUEM_CHAMOU) {
      pararReconexao();
      agendarReconexao(0);
      agendarAvisoDeFalha();
    }
  });

  function tocarVideoRemoto() {
    // Alguns navegadores bloqueiam o som automático: aí aparece o botão "Ativar o som".
    videoRemoto.play().catch(() => mostrarSe(botaoSom, true));
  }

  botaoSom.addEventListener("click", () => {
    mostrarSe(botaoSom, false);
    videoRemoto.play().catch(() => {});
  });

  // --- Canal de dados: conversa e avisos de microfone/câmera/tela ---
  // Os recados são JSON: {tipo: "texto", texto} ou {tipo: "estado", microfone, video, tela}.
  function prepararCanal(novo) {
    canal = novo;
    novo.onopen = () => {
      if (novo === canal) {
        liberarConversa(true);
        enviarEstado(); // o outro já fica sabendo se o meu microfone está desligado
      }
    };
    novo.onclose = () => {
      if (novo === canal) {
        liberarConversa(false);
      }
    };
    novo.onmessage = (evento) => {
      if (novo === canal) {
        receberRecado(evento.data);
      }
    };
  }

  function canalAberto() {
    return canal?.readyState === "open";
  }

  function mandarRecado(recado) {
    if (!canalAberto()) {
      return false;
    }
    canal.send(JSON.stringify(recado));
    return true;
  }

  function receberRecado(dados) {
    // O recado vem do outro navegador: confere tudo antes de usar.
    if (typeof dados !== "string" || dados.length > LIMITE_DO_RECADO) {
      return;
    }
    let recado;
    try {
      recado = JSON.parse(dados);
    } catch (erro) {
      return;
    }
    if (recado?.tipo === "texto" && typeof recado.texto === "string") {
      const texto = recado.texto.trim().slice(0, LIMITE_DA_MENSAGEM);
      if (texto) {
        escreverNaConversa(NOME_DO_OUTRO, texto, { minha: false });
        mostrarRecadoNaTelaCheia(texto);
      }
    } else if (recado?.tipo === "estado") {
      estadoDoOutro = {
        microfone: recado.microfone !== false,
        video: recado.video !== false,
        tela: recado.tela === true,
      };
      atualizarIndicadoresDoOutro();
    }
  }

  function meuEstado() {
    const microfone = midiaLocal?.getAudioTracks()[0];
    const camera = midiaLocal?.getVideoTracks()[0];
    return {
      tipo: "estado",
      microfone: Boolean(microfone?.enabled),
      video: Boolean(telaCompartilhada || camera?.enabled),
      tela: Boolean(telaCompartilhada),
    };
  }

  function enviarEstado() {
    mandarRecado(meuEstado());
  }

  function atualizarIndicadoresDoOutro() {
    // Antes de o canal abrir não sabemos o estado do outro: nada aparece.
    const sabemos = canalAberto();
    mostrarSe(outroSemVideo, sabemos && !estadoDoOutro.video);
    mostrarSe(outroMudo, sabemos && !estadoDoOutro.microfone);
    mostrarSe(outroTela, sabemos && estadoDoOutro.tela);
  }

  // --- Conversa (chat) ---
  function horaAgora() {
    return new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }

  function escreverNaConversa(autor, texto, { minha }) {
    // textContent (e nunca innerHTML): o texto do outro aparece como texto, sem virar código.
    const item = document.createElement("li");
    item.className = minha ? "ml-8 flex flex-col items-end" : "mr-8 flex flex-col items-start";
    const cabecalho = document.createElement("p");
    cabecalho.className = "mb-1 text-xs text-slate-500";
    cabecalho.textContent = `${autor} · ${horaAgora()}`;
    const corpo = document.createElement("p");
    corpo.className = minha
      ? "whitespace-pre-wrap break-words rounded-lg bg-[#1F4E8C] px-3 py-2 text-white"
      : "whitespace-pre-wrap break-words rounded-lg bg-[#F5F7FA] px-3 py-2 text-slate-800";
    corpo.textContent = texto;
    item.append(cabecalho, corpo);
    adicionarNaConversa(item);
  }

  function escreverAvisoNaConversa(texto) {
    const item = document.createElement("li");
    item.className = "text-center text-xs text-slate-500";
    item.textContent = `${texto} (${horaAgora()})`;
    adicionarNaConversa(item);
  }

  function adicionarNaConversa(item) {
    listaDaConversa.append(item);
    listaDaConversa.scrollTop = listaDaConversa.scrollHeight;
  }

  let conversaJaAbriu = false;

  function liberarConversa(liberar) {
    campoConversa.disabled = !liberar;
    botaoEnviar.disabled = !liberar;
    campoConversa.placeholder = liberar
      ? `Mensagem para ${NOME_DO_OUTRO}`
      : conversaJaAbriu
        ? "A conversa volta quando o outro voltar"
        : "A conversa abre quando o outro entrar";
    conversaJaAbriu ||= liberar;
    atualizarIndicadoresDoOutro();
  }

  formConversa.addEventListener("submit", (evento) => {
    evento.preventDefault(); // a mensagem não vai para o portal
    const texto = campoConversa.value.trim().slice(0, LIMITE_DA_MENSAGEM);
    if (!texto || !mandarRecado({ tipo: "texto", texto })) {
      return;
    }
    escreverNaConversa("Você", texto, { minha: true });
    campoConversa.value = "";
    campoConversa.focus();
  });

  // Na tela cheia a conversa não aparece: a mensagem nova surge por alguns segundos no vídeo.
  let relogioDoRecado = null;

  function mostrarRecadoNaTelaCheia(texto) {
    if (document.fullscreenElement !== palco) {
      return;
    }
    const curto = texto.length > 140 ? `${texto.slice(0, 140)}...` : texto;
    recadoNaTelaCheia.textContent = `${NOME_DO_OUTRO}: ${curto}`;
    recadoNaTelaCheia.classList.remove("hidden");
    clearTimeout(relogioDoRecado);
    relogioDoRecado = setTimeout(() => recadoNaTelaCheia.classList.add("hidden"), TEMPO_DO_RECADO_NA_TELA_CHEIA);
  }

  // --- Botões: microfone, câmera, compartilhar a tela e tela cheia ---
  function marcarBotao(botao, { desligado, ativo = false, rotulo, desativado = false }) {
    // data-desligado (vermelho) e data-ativo (branco) mudam a cor pelo Tailwind.
    botao.toggleAttribute("data-desligado", desligado);
    botao.toggleAttribute("data-ativo", ativo);
    botao.disabled = desativado;
    botao.setAttribute("aria-label", rotulo);
    botao.title = rotulo;
    const trocarIcone = desligado || ativo;
    botao.querySelector("[data-icone-ligado]").classList.toggle("hidden", trocarIcone);
    botao.querySelector("[data-icone-desligado]").classList.toggle("hidden", !trocarIcone);
  }

  function atualizarBotoes() {
    const microfone = midiaLocal?.getAudioTracks()[0];
    marcarBotao(botaoMicrofone, {
      desligado: !microfone?.enabled,
      desativado: !microfone,
      rotulo: !microfone ? "Sem microfone" : microfone.enabled ? "Desligar o microfone" : "Ligar o microfone",
    });
    const camera = midiaLocal?.getVideoTracks()[0];
    marcarBotao(botaoCamera, {
      desligado: !camera?.enabled,
      desativado: !camera,
      rotulo: !camera ? "Sem câmera" : camera.enabled ? "Desligar a câmera" : "Ligar a câmera",
    });
    marcarBotao(botaoTela, {
      desligado: false,
      ativo: Boolean(telaCompartilhada),
      rotulo: telaCompartilhada ? "Parar de compartilhar a tela" : "Compartilhar a tela",
    });
    const emTelaCheia = document.fullscreenElement === palco;
    marcarBotao(botaoTelaCheia, {
      desligado: false,
      ativo: emTelaCheia,
      rotulo: emTelaCheia ? "Sair da tela cheia" : "Tela cheia",
    });
  }

  function alternarFaixa(faixa) {
    // enabled = false: a faixa continua na ligação, mas manda silêncio (ou imagem preta).
    if (!faixa) {
      return;
    }
    faixa.enabled = !faixa.enabled;
    atualizarBotoes();
    mostrarMidiaLocal();
    enviarEstado();
  }

  botaoMicrofone.addEventListener("click", () => alternarFaixa(midiaLocal?.getAudioTracks()[0]));
  botaoCamera.addEventListener("click", () => alternarFaixa(midiaLocal?.getVideoTracks()[0]));

  async function trocarVideoEnviado() {
    // replaceTrack troca a câmera pela tela (ou o contrário) sem negociar a ligação de novo.
    if (!enviadores.video) {
      return;
    }
    try {
      await enviadores.video.replaceTrack(faixaParaEnviar("video"));
    } catch (erro) {
      console.warn("Não foi possível trocar o vídeo enviado:", erro);
    }
  }

  async function compartilharTela() {
    if (telaCompartilhada) {
      pararDeCompartilhar();
      return;
    }
    try {
      telaCompartilhada = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    } catch (erro) {
      // NotAllowedError: a pessoa desistiu na janela do navegador. Não é erro.
      if (erro.name !== "NotAllowedError") {
        mostrarAviso("Não foi possível compartilhar a tela neste navegador.");
      }
      return;
    }
    if (!ativa) {
      telaCompartilhada.getTracks().forEach((faixa) => faixa.stop());
      telaCompartilhada = null;
      return;
    }
    const faixa = telaCompartilhada.getVideoTracks()[0];
    faixa.contentHint = "detail"; // prioriza a nitidez do texto, e não a fluidez do movimento
    // A barra do navegador também tem um botão "Parar de compartilhar".
    faixa.addEventListener("ended", pararDeCompartilhar);
    await depoisDeTrocarATela();
  }

  async function pararDeCompartilhar() {
    if (!telaCompartilhada) {
      return;
    }
    telaCompartilhada.getTracks().forEach((faixa) => faixa.stop());
    telaCompartilhada = null;
    await depoisDeTrocarATela();
  }

  async function depoisDeTrocarATela() {
    await trocarVideoEnviado();
    mostrarMidiaLocal();
    atualizarBotoes();
    enviarEstado();
  }

  botaoTela.addEventListener("click", compartilharTela);

  botaoTelaCheia.addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      palco.requestFullscreen().catch(() => {});
    }
  });

  document.addEventListener("fullscreenchange", () => {
    atualizarBotoes();
    if (!document.fullscreenElement) {
      recadoNaTelaCheia.classList.add("hidden");
    }
  });

  // Celular (e navegador antigo) não compartilha a tela; o iPhone não põe um <div> em tela cheia.
  mostrarSe(botaoTela, Boolean(navigator.mediaDevices?.getDisplayMedia));
  mostrarSe(botaoTelaCheia, Boolean(document.fullscreenEnabled));

  // --- Câmera e microfone ---
  const ERROS_DA_MIDIA = {
    NotAllowedError:
      "Você não permitiu o uso da câmera e do microfone. Clique no cadeado ao lado do " +
      "endereço do site, permita os dois e recarregue a página.",
    NotReadableError:
      "A câmera ou o microfone está sendo usado por outro programa (Teams, Zoom ou outra " +
      "aba). Feche o programa e recarregue a página.",
  };
  const AINDA_VE = " Você vê e ouve o outro, mas ele não vê nem ouve você.";

  async function pegarMidia() {
    // O navegador só libera a câmera em página segura: https:// ou http://localhost.
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      avisarSobreAMidia(
        "A câmera e o microfone só funcionam em página segura (endereço com https://). " +
          "No computador, abra o portal por http://localhost:8000." + AINDA_VE
      );
      return null;
    }
    try {
      return await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    } catch (erro) {
      if (erro.name !== "NotFoundError" && erro.name !== "OverconstrainedError") {
        avisarSobreAMidia((ERROS_DA_MIDIA[erro.name] || "Não foi possível usar a câmera e o microfone.") + AINDA_VE);
        return null;
      }
    }
    // Sem câmera (comum em computador de laboratório): tenta entrar só com o microfone.
    try {
      const soAudio = await navigator.mediaDevices.getUserMedia({ audio: true });
      avisarSobreAMidia("Nenhuma câmera foi encontrada neste computador. Você entra só com o microfone.");
      return soAudio;
    } catch (erro) {
      avisarSobreAMidia("Nenhuma câmera nem microfone foi encontrado neste computador." + AINDA_VE);
      return null;
    }
  }

  function mostrarMidiaLocal() {
    // Na miniatura: a tela compartilhada, ou a câmera ligada, ou o aviso.
    const camera = midiaLocal?.getVideoTracks()[0];
    const imagem = telaCompartilhada || (camera?.enabled ? midiaLocal : null);
    if (imagem && videoLocal.srcObject !== imagem) {
      videoLocal.srcObject = imagem;
    }
    videoLocal.classList.toggle("invisible", !imagem);
    videoLocal.classList.toggle("-scale-x-100", !telaCompartilhada); // a tela não é espelhada
    semCamera.textContent = camera ? "Câmera desligada" : "Sem câmera";
    mostrarSe(semCamera, !imagem);
  }

  function pararMidia() {
    midiaLocal?.getTracks().forEach((faixa) => faixa.stop());
    telaCompartilhada?.getTracks().forEach((faixa) => faixa.stop());
    midiaLocal = null;
    telaCompartilhada = null;
  }

  async function buscarServidoresIce() {
    try {
      const resposta = await fetch(URL_ICE, { credentials: "same-origin", cache: "no-store" });
      if (resposta.ok) {
        return (await resposta.json()).iceServers;
      }
      if (resposta.status === 400 || resposta.redirected) {
        terminar(); // chamada encerrada ou login vencido
      }
    } catch (erro) {
      // sem rede: segue sem STUN/TURN (funciona entre abas do mesmo computador)
    }
    return [];
  }

  // --- Entrar, sair e terminar ---
  async function iniciar() {
    atualizarBotoes();
    if (!window.RTCPeerConnection) {
      mostrarEstado("Navegador sem suporte", { cor: "problema", textoDaCapa: "Este navegador não faz videochamadas." });
      mostrarAviso('Este navegador não faz videochamadas. Use o Chrome, o Edge ou o Firefox atualizados, ou o link "Entrar pelo Jitsi".');
      return;
    }
    mostrarEstado("Preparando câmera e microfone...", {
      textoDaCapa: "Se o navegador perguntar, permita o uso da câmera e do microfone.",
    });
    midiaLocal = await pegarMidia();
    mostrarMidiaLocal();
    atualizarBotoes();
    servidoresIce = await buscarServidoresIce();
    if (!ativa) {
      return;
    }
    await enviarSinal("entrei");
    mostrarEstado("Aguardando o outro entrar...");
    consultar();
  }

  function desligar({ avisarOOutro = true } = {}) {
    // Para tudo nesta aba e avisa o outro ("saiu"). Seguro de chamar mais de uma vez.
    if (!ativa) {
      return;
    }
    ativa = false;
    clearTimeout(proximaConsulta);
    if (avisarOOutro) {
      postar(corpoDoSinal("saiu"), { keepalive: true });
    }
    fecharConexao();
    pararMidia();
    videoLocal.srcObject = null;
    [botaoMicrofone, botaoCamera, botaoTela, botaoTelaCheia].forEach((botao) => {
      botao.disabled = true;
    });
  }

  function terminar() {
    // Chamada encerrada (ou login vencido): recarrega, e o portal mostra a tela certa.
    // Não manda "saiu": o portal recusaria o sinal, e o outro também vê que a chamada acabou.
    desligar({ avisarOOutro: false });
    window.location.reload();
  }

  sala.querySelector("[data-sair]").addEventListener("click", () => {
    desligar();
    window.location.href = URL_INICIO;
  });

  // Plano B: ao abrir o Jitsi, esta sala desliga para não usar a câmera duas vezes.
  sala.querySelector("[data-link-jitsi]").addEventListener("click", () => {
    desligar();
    mostrarEstado("Chamada aberta no Jitsi", {
      textoDaCapa: "A chamada continua no Jitsi, em outra aba. Para voltar para cá, recarregue a página.",
    });
  });

  // Fechar a aba, recarregar ou ir para outra tela também avisa o outro ("saiu").
  window.addEventListener("pagehide", () => desligar());
  // Se o navegador devolver a página da memória (botão Voltar), começa de novo.
  window.addEventListener("pageshow", (evento) => {
    if (evento.persisted) {
      window.location.reload();
    }
  });

  iniciar();
})();
