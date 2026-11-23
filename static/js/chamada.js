// Sala de vídeo própria (videochamadas/_sala_propria.html). JavaScript puro, sem biblioteca.
//
// O vídeo e o áudio vão DIRETO de um navegador ao outro (WebRTC): não passam pelo portal e
// não são gravados. O portal só leva os "sinais", recados curtos que os dois navegadores
// trocam para se encontrar:
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

(() => {
  const sala = document.querySelector("[data-sala-propria]");
  if (!sala) {
    return;
  }

  // --- Configuração vinda do template ---
  const URL_SINAL = sala.dataset.urlSinal;
  const URL_ICE = sala.dataset.urlIce;
  const URL_INICIO = sala.dataset.urlInicio;
  const SOU_QUEM_CHAMOU = sala.dataset.souQuemChamou === "true";
  const TOKEN_CSRF = sala.querySelector("[name=csrfmiddlewaretoken]").value;

  const INTERVALO_CONECTANDO = 1000; // ms entre as consultas enquanto conecta
  const INTERVALO_CONECTADO = 5000; // depois de conectado, só para perceber "saiu"/"encerrada"
  const INTERVALO_SEM_REDE = 3000; // o portal não respondeu: tenta de novo com calma
  const ESPERA_DOS_CANDIDATOS = 200; // junta os candidatos que aparecem nesse intervalo

  // --- Elementos da tela ---
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

  // --- Situação da sala ---
  const minhaSessao = sortearSessao();
  let ultimoSinal = Number(sala.dataset.ultimoSinal) || 0; // último sinal já lido
  let conexao = null; // RTCPeerConnection: a ligação direta com o outro navegador
  let midiaLocal = null; // câmera e microfone (ou null, se não deu para usar)
  let videoDoOutro = null; // MediaStream com o que chega do outro
  let sessaoDoOutro = null; // aba do outro com quem estamos conversando
  let candidatosPendentes = []; // candidatos que chegaram antes da oferta/resposta
  let filaDeEnvio = Promise.resolve(); // os sinais saem um de cada vez, na ordem
  let conectado = false;
  let ativa = true; // false depois de sair ou de a chamada acabar
  let servidoresIce = [];
  let proximaConsulta = null;

  function sortearSessao() {
    // crypto.getRandomValues funciona mesmo fora do HTTPS (o randomUUID, não).
    const numeros = crypto.getRandomValues(new Uint8Array(8));
    return Array.from(numeros, (n) => n.toString(16).padStart(2, "0")).join("");
  }

  function pausa(milissegundos) {
    return new Promise((pronto) => setTimeout(pronto, milissegundos));
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
    capa.classList.toggle("hidden", !mostrarCapa);
    capa.classList.toggle("flex", mostrarCapa);
    capaTexto.textContent = textoDaCapa;
  }

  // O aviso da câmera/microfone fica guardado: ele continua valendo depois de conectar,
  // enquanto o aviso de "não conectou" some quando a conexão volta.
  let avisoDaMidia = "";

  function mostrarAviso(texto) {
    avisoTexto.textContent = texto;
    aviso.classList.toggle("hidden", !texto);
    aviso.classList.toggle("flex", Boolean(texto));
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
      await receberOferta(sessao, conteudo.descricao);
    } else if (sinal.tipo === "resposta") {
      await receberResposta(sessao, conteudo.descricao);
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
      await criarOferta();
    } else {
      // O convidado avisa a aba nova de quem chamou que está aqui; ela responde com a oferta.
      enviarSinal("entrei", { para_sessao: sessao });
    }
  }

  async function criarOferta() {
    novaConexao();
    const oferta = await conexao.createOffer();
    await conexao.setLocalDescription(oferta);
    enviarSinal("oferta", { para_sessao: sessaoDoOutro, descricao: descricaoLocal() });
  }

  async function receberOferta(sessao, descricao) {
    if (SOU_QUEM_CHAMOU || !descricao) {
      return; // só o convidado recebe oferta
    }
    if (sessao !== sessaoDoOutro || !conexao) {
      sessaoDoOutro = sessao;
      novaConexao();
    }
    mostrarEstado("Conectando...", { textoDaCapa: "Conectando..." });
    await conexao.setRemoteDescription(descricao);
    await aplicarCandidatosPendentes();
    // O convidado põe a câmera e o microfone depois de ler a oferta, nos mesmos "canais".
    adicionarMidiaLocal();
    const resposta = await conexao.createAnswer();
    await conexao.setLocalDescription(resposta);
    enviarSinal("resposta", { para_sessao: sessao, descricao: descricaoLocal() });
  }

  async function receberResposta(sessao, descricao) {
    if (!SOU_QUEM_CHAMOU || !conexao || sessao !== sessaoDoOutro || !descricao) {
      return;
    }
    if (conexao.signalingState !== "have-local-offer") {
      return; // resposta repetida ou atrasada
    }
    await conexao.setRemoteDescription(descricao);
    await aplicarCandidatosPendentes();
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
    await conexao.addIceCandidate(candidato);
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
    candidatosPendentes = [];
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

    if (SOU_QUEM_CHAMOU) {
      // Quem oferece já põe a câmera e o microfone. Se faltar algum, pede só para receber.
      adicionarMidiaLocal();
      for (const tipo of ["audio", "video"]) {
        const temCanal = esta.getTransceivers().some((t) => t.receiver.track.kind === tipo);
        if (!temCanal) {
          esta.addTransceiver(tipo, { direction: "recvonly" });
        }
      }
    }
  }

  function adicionarMidiaLocal() {
    if (!midiaLocal || !conexao) {
      return;
    }
    const jaEnviadas = conexao.getSenders().map((enviador) => enviador.track);
    for (const faixa of midiaLocal.getTracks()) {
      if (!jaEnviadas.includes(faixa)) {
        conexao.addTrack(faixa, midiaLocal);
      }
    }
  }

  function fecharConexao() {
    if (conexao) {
      conexao.close();
      conexao = null;
    }
    conectado = false;
    candidatosPendentes = [];
    videoRemoto.srcObject = null;
    botaoSom.classList.add("hidden");
    botaoSom.classList.remove("flex");
  }

  function atualizarEstadoDaConexao() {
    const estado = conexao.connectionState;
    if (estado === "connected") {
      conectado = true;
      mostrarAviso(avisoDaMidia); // some o aviso de "não conectou"; o da câmera continua
      mostrarEstado("Conectado", { cor: "conectado", mostrarCapa: false });
    } else if (estado === "disconnected") {
      // A internet oscilou. O navegador tenta voltar sozinho; o vídeo fica parado até lá.
      conectado = false;
      mostrarEstado("Reconectando...", { mostrarCapa: false });
      consultarJa(); // talvez o outro tenha recarregado a página: confere os sinais agora
    } else if (estado === "failed") {
      conectado = false;
      consultarJa();
      mostrarEstado("Não foi possível conectar", {
        cor: "problema",
        textoDaCapa: "Não foi possível conectar os dois computadores.",
      });
      mostrarAviso(
        "A conexão direta entre os dois computadores não funcionou. Isso costuma acontecer " +
          "quando cada um está numa rede diferente (como dois roteadores de celular) e o " +
          "servidor TURN não está configurado. Recarreguem a página ou usem o link " +
          '"Não conectou? Entrar pelo Jitsi", abaixo.'
      );
    } else if (estado === "connecting") {
      mostrarEstado("Conectando...", { mostrarCapa: !conectado, textoDaCapa: "Conectando..." });
    }
  }

  function tocarVideoRemoto() {
    // Alguns navegadores bloqueiam o som automático: aí aparece o botão "Ativar o som".
    videoRemoto.play().catch(() => {
      botaoSom.classList.remove("hidden");
      botaoSom.classList.add("flex");
    });
  }

  botaoSom.addEventListener("click", () => {
    botaoSom.classList.add("hidden");
    botaoSom.classList.remove("flex");
    videoRemoto.play().catch(() => {});
  });

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
    const temVideo = Boolean(midiaLocal?.getVideoTracks().length);
    if (temVideo) {
      videoLocal.srcObject = midiaLocal;
    }
    videoLocal.classList.toggle("invisible", !temVideo);
    semCamera.classList.toggle("hidden", temVideo);
    semCamera.classList.toggle("flex", !temVideo);
  }

  function pararMidia() {
    midiaLocal?.getTracks().forEach((faixa) => faixa.stop());
    midiaLocal = null;
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
