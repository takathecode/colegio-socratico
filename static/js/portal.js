// Comportamentos das telas: ícones, barra lateral, mostrar senha, botão "carregando",
// janelas modais, anexos e filtros.

// Desenha os ícones Lucide. O "if" evita erro caso o CDN esteja fora do ar.
if (window.lucide) {
  window.lucide.createIcons();
}

// --- Barra lateral ---
// O botão do topo recolhe o menu no computador e abre o menu no celular.
const raiz = document.documentElement;
const telaGrande = window.matchMedia("(min-width: 1024px)");

function fecharMenuCelular() {
  delete raiz.dataset.menu;
}

document.querySelector("[data-alternar-menu]")?.addEventListener("click", () => {
  if (!telaGrande.matches) {
    if (raiz.dataset.menu === "aberto") {
      fecharMenuCelular();
    } else {
      raiz.dataset.menu = "aberto";
    }
    return;
  }

  const recolher = raiz.dataset.sidebar !== "recolhida";
  if (recolher) {
    raiz.dataset.sidebar = "recolhida";
  } else {
    delete raiz.dataset.sidebar;
  }
  // A preferência é só uma conveniência: a página funciona se o navegador bloquear o armazenamento.
  try {
    localStorage.setItem("barra-lateral", recolher ? "recolhida" : "aberta");
  } catch (erro) {}
});

document.querySelector("[data-fundo-menu]")?.addEventListener("click", fecharMenuCelular);
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") {
    fecharMenuCelular();
  }
});

// --- Mostrar ou esconder a senha ---
document.querySelectorAll("[data-mostrar-senha]").forEach((botao) => {
  botao.addEventListener("click", () => {
    const campo = botao.parentElement.querySelector("input");
    const mostrar = campo.type === "password";
    campo.type = mostrar ? "text" : "password";
    botao.setAttribute("aria-pressed", String(mostrar));
    botao.setAttribute("aria-label", mostrar ? "Esconder senha" : "Mostrar senha");
    botao.querySelector('[data-olho="fechado"]').classList.toggle("hidden", mostrar);
    botao.querySelector('[data-olho="aberto"]').classList.toggle("hidden", !mostrar);
  });
});

// --- Requisitos da senha nova (componentes/checklist_senha.html) ---
// Só ajuda a pessoa enquanto digita: quem aceita ou recusa a senha é o servidor
// (AUTH_PASSWORD_VALIDATORS). Cada item troca de ícone e de texto escondido, não só de cor.
const REGRAS_DA_SENHA = {
  tamanho: (senha) => senha.length >= 10 && senha.length <= 128,
  maiuscula: (senha) => /[A-Z]/.test(senha),
  minuscula: (senha) => /[a-z]/.test(senha),
  numero: (senha) => /[0-9]/.test(senha),
  especial: (senha) => /[^A-Za-z0-9]/.test(senha),
  iguais: (senha, confirmacao) => senha.length > 0 && senha === confirmacao,
};

document.querySelectorAll("[data-checklist-senha]").forEach((lista) => {
  const campo = document.getElementById(lista.dataset.checklistSenha);
  const confirmacao = document.getElementById(lista.dataset.confirmacao);
  const resumo = lista.querySelector("[data-resumo]");
  if (!campo) return;

  function atualizar() {
    const itens = lista.querySelectorAll("[data-regra]");
    let atendidos = 0;
    itens.forEach((item) => {
      const ok = REGRAS_DA_SENHA[item.dataset.regra](campo.value, confirmacao?.value ?? "");
      if (ok) atendidos += 1;
      item.classList.toggle("text-green-800", ok);
      item.classList.toggle("text-slate-600", !ok);
      item.querySelector("[data-ok]").classList.toggle("hidden", !ok);
      item.querySelector("[data-pendente]").classList.toggle("hidden", ok);
      item.querySelector("[data-estado]").textContent = ok ? "(atendido)" : "(não atendido)";
    });
    // Lido pelo leitor de tela (aria-live="polite") sem interromper a digitação.
    resumo.textContent = `${atendidos} de ${itens.length} requisitos da senha atendidos.`;
  }

  campo.addEventListener("input", atualizar);
  confirmacao?.addEventListener("input", atualizar);
});

// --- Menu do avatar (topo) ---
// O <details> abre e fecha sozinho; aqui ele fecha ao clicar fora, ao apertar Esc e ao abrir a foto.
const menuDoUsuario = document.querySelector("details[data-menu-usuario]");
if (menuDoUsuario) {
  document.addEventListener("click", (evento) => {
    if (menuDoUsuario.open && !menuDoUsuario.contains(evento.target)) menuDoUsuario.open = false;
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && menuDoUsuario.open) {
      menuDoUsuario.open = false;
      menuDoUsuario.querySelector("summary").focus();
    }
  });
  menuDoUsuario.querySelectorAll("[data-abrir-modal]").forEach((botao) => {
    botao.addEventListener("click", () => (menuDoUsuario.open = false));
  });
}

// --- Botão "carregando" ---
function marcarCarregando(formulario, carregando) {
  const botao = formulario.querySelector('button[type="submit"]');
  botao.disabled = carregando;
  botao.querySelector('[data-estado="normal"]').classList.toggle("hidden", carregando);
  const estadoCarregando = botao.querySelector('[data-estado="carregando"]');
  estadoCarregando.classList.toggle("hidden", !carregando);
  estadoCarregando.classList.toggle("flex", carregando);
  formulario.querySelector("[data-aviso-carregando]")?.classList.toggle("hidden", !carregando);
}

const formularios = document.querySelectorAll("form[data-carregando]");
formularios.forEach((formulario) => {
  formulario.addEventListener("submit", () => marcarCarregando(formulario, true));
});

// Ao voltar pelo botão do navegador, a página pode reaparecer ainda no estado "carregando".
window.addEventListener("pageshow", () => {
  formularios.forEach((formulario) => marcarCarregando(formulario, false));
});

// --- Janelas modais (elemento <dialog>) ---
document.querySelectorAll("[data-abrir-modal]").forEach((botao) => {
  botao.addEventListener("click", () => {
    document.getElementById(botao.dataset.abrirModal)?.showModal();
  });
});

document.querySelectorAll("[data-fechar-modal]").forEach((botao) => {
  botao.addEventListener("click", () => botao.closest("dialog").close());
});

// Formulário com erro volta com a janela aberta, para o usuário ver o que corrigir.
document.querySelectorAll("dialog[data-abrir-ao-carregar]").forEach((janela) => janela.showModal());

// --- Foto de perfil (componentes/foto_perfil.html) ---
// 1) O campo do arquivo só é liberado depois de a pessoa confirmar que leu as regras.
// 2) A foto escolhida é recortada em quadrado e reduzida para 512×512 em JPEG. Isso deixa o
//    envio leve e apaga os metadados (EXIF), como a localização GPS das fotos de celular.
// O servidor confere tudo de novo (apps/contas/foto.py): estas checagens só ajudam a pessoa.
const LADO_DA_FOTO = 512;
const TIPOS_DE_FOTO = ["image/jpeg", "image/png", "image/webp"];
const LIMITE_ORIGINAL = 20 * 1024 * 1024; // fotos de celular grandes são reduzidas antes do envio

async function reduzirFoto(arquivo) {
  const imagem = await createImageBitmap(arquivo); // já respeita a rotação da foto do celular
  const lado = Math.min(imagem.width, imagem.height);
  const tela = document.createElement("canvas");
  tela.width = tela.height = Math.min(LADO_DA_FOTO, lado);
  const contexto = tela.getContext("2d");
  contexto.fillStyle = "#fff"; // PNG transparente fica com fundo branco, e não preto
  contexto.fillRect(0, 0, tela.width, tela.height);
  // Recorte central: pega o maior quadrado no meio da imagem.
  contexto.drawImage(imagem, (imagem.width - lado) / 2, (imagem.height - lado) / 2, lado, lado,
    0, 0, tela.width, tela.height);
  imagem.close();
  const blob = await new Promise((pronto) => tela.toBlob(pronto, "image/jpeg", 0.9));
  if (!blob) {
    throw new Error("O navegador não conseguiu converter a imagem.");
  }
  return new File([blob], "foto.jpg", { type: "image/jpeg" });
}

document.querySelectorAll("form[data-form-foto]").forEach((formulario) => {
  const aceite = formulario.querySelector("[data-foto-aceite]");
  const campo = formulario.querySelector('input[type="file"]');
  const previa = formulario.querySelector("[data-foto-previa]");
  const atual = formulario.querySelector("[data-foto-atual]");
  const erro = formulario.querySelector("[data-foto-erro]");
  const dica = formulario.querySelector("[data-foto-dica]");
  const limite = Number(campo.dataset.limite);
  let enderecoDaPrevia = null;
  let processando = false;

  function limparPrevia() {
    if (enderecoDaPrevia) {
      URL.revokeObjectURL(enderecoDaPrevia); // libera a memória da prévia anterior
      enderecoDaPrevia = null;
    }
    previa.removeAttribute("src");
    previa.classList.add("hidden");
    atual.classList.remove("hidden");
  }

  function mostrarErro(texto) {
    erro.textContent = texto;
    campo.setAttribute("aria-invalid", texto ? "true" : "false");
  }

  function atualizarLiberacao() {
    campo.disabled = !aceite.checked;
    dica.hidden = aceite.checked;
    if (!aceite.checked) {
      campo.value = "";
      limparPrevia();
      mostrarErro("");
    }
  }

  campo.addEventListener("change", async () => {
    mostrarErro("");
    limparPrevia();
    const arquivo = campo.files[0];
    if (!arquivo) {
      return;
    }
    if (!TIPOS_DE_FOTO.includes(arquivo.type)) {
      campo.value = "";
      mostrarErro("Escolha uma imagem JPG, PNG ou WebP.");
      return;
    }
    if (arquivo.size > LIMITE_ORIGINAL) {
      campo.value = "";
      mostrarErro("A imagem é grande demais. Escolha uma com até 20 MB.");
      return;
    }

    processando = true;
    let final = arquivo;
    try {
      final = await reduzirFoto(arquivo);
      // Troca o arquivo do campo pela versão reduzida (DataTransfer é o jeito padrão de montar a lista).
      const lista = new DataTransfer();
      lista.items.add(final);
      campo.files = lista.files;
    } catch (falha) {
      // Navegador antigo: envia a foto original, e o servidor confere o tamanho.
      final = arquivo;
    } finally {
      processando = false;
    }

    if (final.size > limite) {
      campo.value = "";
      mostrarErro("A foto deve ter no máximo 2 MB.");
      return;
    }
    enderecoDaPrevia = URL.createObjectURL(final);
    previa.src = enderecoDaPrevia;
    previa.classList.remove("hidden");
    atual.classList.add("hidden");
  });

  // Não envia enquanto a foto ainda está sendo reduzida (leva uma fração de segundo).
  formulario.addEventListener("submit", (evento) => {
    if (processando) {
      evento.preventDefault();
      evento.stopImmediatePropagation();
    }
  }, true);

  aceite.addEventListener("change", atualizarLiberacao);
  // Ao fechar a janela, tudo volta ao começo: a confirmação vale só para aquele envio.
  formulario.closest("dialog")?.addEventListener("close", () => {
    formulario.reset();
    atualizarLiberacao();
  });
  atualizarLiberacao();
});

// --- Modal de justificativa: a disciplina filtra as datas das faltas ---
document.querySelectorAll("form[data-filtro-faltas]").forEach((formulario) => {
  const disciplina = formulario.querySelector("[data-disciplina-da-falta]");
  const datas = formulario.querySelector('select[name="frequencia"]');
  // Guarda todas as opções, pois alguns navegadores não escondem <option> com CSS.
  const todasAsDatas = [...datas.options];

  function mostrarDatasDaDisciplina() {
    const selecionada = datas.value;
    datas.replaceChildren(
      ...todasAsDatas.filter((opcao) => opcao.dataset.oferta === disciplina.value)
    );
    datas.value = selecionada;
    if (datas.selectedIndex < 0) {
      datas.selectedIndex = 0;
    }
  }

  // Começa na disciplina da falta já selecionada pelo servidor.
  disciplina.value = datas.selectedOptions[0]?.dataset.oferta ?? disciplina.value;
  mostrarDatasDaDisciplina();
  disciplina.addEventListener("change", mostrarDatasDaDisciplina);
});

// --- Campo de anexo: mostra o arquivo escolhido e permite remover ---
function tamanhoLegivel(bytes) {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

document.querySelectorAll("[data-anexo]").forEach((area) => {
  const campo = area.querySelector('input[type="file"]');
  const nome = area.querySelector("[data-anexo-nome]");
  const tamanho = area.querySelector("[data-anexo-tamanho]");
  const remover = area.querySelector("[data-anexo-remover]");
  const nomeOriginal = nome.textContent;
  const tamanhoOriginal = tamanho?.textContent;

  function atualizar() {
    const arquivo = campo.files[0];
    nome.textContent = arquivo ? arquivo.name : nomeOriginal;
    if (tamanho) {
      tamanho.textContent = arquivo ? tamanhoLegivel(arquivo.size) : tamanhoOriginal;
    }
    remover.classList.toggle("hidden", !arquivo);
    remover.classList.toggle("flex", Boolean(arquivo));
  }

  campo.addEventListener("change", atualizar);
  remover.addEventListener("click", () => {
    campo.value = "";
    atualizar();
  });
});

// --- Pequenos ajustes ---
// Filtro que recarrega a página assim que o valor muda.
document.querySelectorAll("[data-enviar-ao-mudar]").forEach((campo) => {
  campo.addEventListener("change", () => campo.form.submit());
});

// Conversa aberta: mostra primeiro as mensagens mais novas.
document.querySelectorAll("[data-rolar-ate-o-fim]").forEach((area) => {
  area.scrollTop = area.scrollHeight;
});

// --- Chamada com biometria simulada ---
// Não existe leitor de verdade: o navegador "lê" a digital de cada aluno, com uma pausa
// curta, e sorteia se ela foi reconhecida. O servidor só recebe o resultado do formulário.
const CHANCE_DE_RECONHECER = 0.9; // 9 em cada 10 leituras dão certo
const TEMPO_DE_LEITURA = 450; // milissegundos por aluno

function esperar(milissegundos) {
  return new Promise((resolver) => setTimeout(resolver, milissegundos));
}

document.querySelectorAll("[data-chamada]").forEach((area) => {
  // Linhas travadas (falta já justificada) não têm data-aluno e ficam de fora.
  const linhas = [...area.querySelectorAll("[data-aluno]")];
  const status = area.querySelector("[data-biometria-status]");
  const leitor = area.querySelector("[data-leitor]");
  const botaoLeitura = area.querySelector("[data-iniciar-biometria]");
  const botaoTodos = area.querySelector("[data-todos-presentes]");

  function marcacao(linha) {
    return linha.querySelector('input[type="radio"]:checked')?.value; // "presente", "falta" ou nada
  }

  function atualizarContadores() {
    const contagem = { presente: 0, falta: 0, pendente: 0 };
    linhas.forEach((linha) => {
      contagem[marcacao(linha) ?? "pendente"] += 1;
    });
    // As faltas travadas também contam como falta.
    contagem.falta += area.querySelectorAll("li:not([data-aluno])").length;
    Object.entries(contagem).forEach(([chave, total]) => {
      area.querySelector(`[data-contador="${chave}"]`).textContent = total;
    });
  }

  function marcar(linha, situacao, metodo) {
    linha.querySelector(`input[value="${situacao}"]`).checked = true;
    linha.querySelector("[data-metodo]").value = metodo;
    linha.querySelector("[data-rotulo-metodo]").textContent =
      metodo === "BIOMETRIA" ? "Biometria" : "Manual";
    atualizarContadores();
  }

  // Marcação feita à mão pelo professor.
  linhas.forEach((linha) => {
    linha.querySelectorAll('input[type="radio"]').forEach((opcao) => {
      opcao.addEventListener("change", () => marcar(linha, opcao.value, "MANUAL"));
    });
  });

  botaoTodos.addEventListener("click", () => {
    linhas.forEach((linha) => {
      if (marcacao(linha) !== "presente") {
        marcar(linha, "presente", "MANUAL");
      }
    });
    status.textContent = "Todos marcados como presentes. Ajuste as faltas e salve.";
  });

  botaoLeitura.addEventListener("click", async () => {
    // Só passa pelo leitor quem ainda não está presente.
    const fila = linhas.filter((linha) => marcacao(linha) !== "presente");
    if (!fila.length) {
      status.textContent = "Todos os alunos já estão presentes.";
      return;
    }

    botaoLeitura.disabled = true;
    botaoTodos.disabled = true;
    leitor.classList.add("animate-pulse");
    let reconhecidos = 0;

    for (const [indice, linha] of fila.entries()) {
      status.textContent = `Lendo a digital de ${linha.dataset.aluno} (${indice + 1} de ${fila.length})...`;
      linha.classList.add("bg-primaria-suave");
      linha.scrollIntoView({ block: "nearest", behavior: "smooth" });
      await esperar(TEMPO_DE_LEITURA);

      if (Math.random() < CHANCE_DE_RECONHECER) {
        marcar(linha, "presente", "BIOMETRIA");
        reconhecidos += 1;
      } else {
        marcar(linha, "falta", "MANUAL");
      }
      linha.classList.remove("bg-primaria-suave");
    }

    leitor.classList.remove("animate-pulse");
    botaoLeitura.disabled = false;
    botaoTodos.disabled = false;
    const naoReconhecidos = fila.length - reconhecidos;
    status.textContent =
      `Leitura concluída: ${reconhecidos} reconhecido(s)` +
      (naoReconhecidos ? ` e ${naoReconhecidos} com falta. Confira antes de salvar.` : ". Agora é só salvar.");
  });

  atualizarContadores();
});

// --- Coordenação ---
// Pede confirmação antes de ações sensíveis, como gerar nova senha ou desativar uma conta.
document.querySelectorAll("form[data-confirmar]").forEach((formulario) => {
  formulario.addEventListener("submit", (evento) => {
    if (!window.confirm(formulario.dataset.confirmar)) evento.preventDefault();
  });
});

// Formulários com mais de um botão (ex.: "Enviar link" e "Gerar senha provisória"): todos os
// botões ficam desativados depois do clique, para o pedido não ser enviado duas vezes.
// O setTimeout espera o navegador montar o envio, que leva o "name" do botão clicado.
document.querySelectorAll("form[data-enviar-uma-vez]").forEach((formulario) => {
  formulario.addEventListener("submit", (evento) => {
    setTimeout(() => {
      if (evento.defaultPrevented) return; // a pessoa cancelou na confirmação
      formulario.querySelectorAll("button[type='submit']").forEach((botao) => (botao.disabled = true));
    }, 0);
  });
});

// Botão "Copiar" da senha provisória. data-copiar tem o id do elemento com o texto.
document.querySelectorAll("[data-copiar]").forEach((botao) => {
  const rotulo = botao.querySelector("[data-rotulo]");
  botao.addEventListener("click", async () => {
    const texto = document.getElementById(botao.dataset.copiar).textContent.trim();
    try {
      await navigator.clipboard.writeText(texto);
      rotulo.textContent = "Copiada!";
    } catch (erro) {
      rotulo.textContent = "Copie manualmente"; // navegador sem permissão de copiar
    }
    setTimeout(() => (rotulo.textContent = "Copiar"), 2500);
  });
});

// --- Videochamada recebida (componentes/chamada_recebida.html) ---
// Em qualquer tela do professor e da coordenação, pergunta ao portal a cada 10 s se alguém
// está chamando (rota videochamadas:recebida). Se estiver, abre a janela com Atender e Recusar.
// É polling, como na sala de vídeo: a Vercel não segura conexões abertas (docs/VIDEOCHAMADA.md).
const janelaDeChamada = document.querySelector("dialog[data-chamada-recebida]");
if (janelaDeChamada) {
  const INTERVALO_COM_A_ABA_ABERTA = 10000;
  const INTERVALO_EM_SEGUNDO_PLANO = 30000; // aba escondida: pergunta com menos frequência
  const RITMO_DO_TOQUE = 1500; // o título da aba pisca neste ritmo; o bipe toca a cada 2 piscadas

  const urlRecebida = janelaDeChamada.dataset.url;
  const tokenCsrf = janelaDeChamada.querySelector("[name=csrfmiddlewaretoken]").value;
  const campoNome = janelaDeChamada.querySelector("[data-chamada-nome]");
  const campoAssunto = janelaDeChamada.querySelector("[data-chamada-assunto]");
  const campoAvatar = janelaDeChamada.querySelector("[data-chamada-avatar]");
  const campoErro = janelaDeChamada.querySelector("[data-chamada-erro]");
  const botaoAtender = janelaDeChamada.querySelector("[data-chamada-atender]");
  const botaoRecusar = janelaDeChamada.querySelector("[data-chamada-recusar]");
  const tituloDaPagina = document.title;

  const ignoradas = new Set(); // chamadas que a pessoa fechou com Esc nesta aba
  let chamadaNaTela = null;
  let proximaPergunta = null;
  let relogioDoToque = null;
  let audio = null;

  function bipe() {
    // Dois tons curtos feitos pelo próprio navegador (Web Audio), sem arquivo de som. Se o
    // navegador bloquear som antes de a pessoa clicar na página, fica só a janela.
    try {
      audio ||= new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume().catch(() => {});
      const agora = audio.currentTime;
      [520, 660].forEach((frequencia, ordem) => {
        const inicio = agora + ordem * 0.25;
        const oscilador = audio.createOscillator();
        const volume = audio.createGain();
        oscilador.frequency.value = frequencia;
        volume.gain.setValueAtTime(0.0001, inicio);
        volume.gain.exponentialRampToValueAtTime(0.08, inicio + 0.02);
        volume.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.2);
        oscilador.connect(volume).connect(audio.destination);
        oscilador.start(inicio);
        oscilador.stop(inicio + 0.22);
      });
    } catch (erro) {
      // navegador sem Web Audio: segue só com a janela
    }
  }

  function comecarATocar() {
    pararDeTocar();
    bipe();
    let piscada = 0;
    relogioDoToque = setInterval(() => {
      piscada += 1;
      document.title = piscada % 2 ? `Chamada de ${chamadaNaTela.nome}` : tituloDaPagina;
      if (piscada % 2 === 0) bipe();
    }, RITMO_DO_TOQUE);
  }

  function pararDeTocar() {
    clearInterval(relogioDoToque);
    relogioDoToque = null;
    document.title = tituloDaPagina;
  }

  function mostrarChamada(chamada) {
    if (chamadaNaTela?.id === chamada.id) return; // já está na tela
    chamadaNaTela = chamada;
    // textContent (e nunca innerHTML): nome e assunto aparecem como texto.
    campoNome.textContent = chamada.nome;
    campoAssunto.textContent = chamada.assunto ? `Assunto: ${chamada.assunto}` : "Sem assunto";
    campoAvatar.replaceChildren();
    if (chamada.foto) {
      const foto = document.createElement("img");
      foto.src = chamada.foto;
      foto.alt = "";
      foto.className = "size-full object-cover";
      campoAvatar.append(foto);
    } else {
      campoAvatar.textContent = chamada.iniciais;
    }
    botaoAtender.href = chamada.url_sala;
    campoErro.classList.add("hidden");
    botaoRecusar.disabled = false;
    if (!janelaDeChamada.open) janelaDeChamada.showModal();
    comecarATocar();
  }

  let fechandoPeloPortal = false;

  function esconderChamada() {
    // Recusou, quem chamou desistiu, outra aba atendeu ou passou o tempo do toque.
    if (!janelaDeChamada.open) return;
    fechandoPeloPortal = true;
    janelaDeChamada.close(); // o evento "close" faz o resto
  }

  janelaDeChamada.addEventListener("close", () => {
    // Fechada pela própria pessoa (Esc): não recusa e não abre de novo nesta aba; o convite
    // continua no sino. Não dá para usar o evento "cancel": o Chrome não o dispara quando a
    // janela abriu sem um clique da pessoa (como aqui, aberta pelo relógio).
    if (!fechandoPeloPortal && chamadaNaTela) ignoradas.add(chamadaNaTela.id);
    fechandoPeloPortal = false;
    pararDeTocar();
    chamadaNaTela = null;
  });
  botaoAtender.addEventListener("click", pararDeTocar);

  botaoRecusar.addEventListener("click", async () => {
    if (!chamadaNaTela) return;
    botaoRecusar.disabled = true;
    try {
      const resposta = await fetch(chamadaNaTela.url_recusar, {
        method: "POST",
        headers: { "X-CSRFToken": tokenCsrf },
        credentials: "same-origin",
      });
      // 400/404: a chamada já foi atendida (em outra aba), encerrada ou não existe mais.
      if (resposta.ok || resposta.status === 400 || resposta.status === 404) {
        esconderChamada();
        return;
      }
    } catch (erro) {
      // sem rede: mostra o aviso abaixo
    }
    campoErro.textContent = "Não foi possível recusar. Confira a internet e tente de novo.";
    campoErro.classList.remove("hidden");
    botaoRecusar.disabled = false;
  });

  let perguntando = false; // trava: nunca duas perguntas ao mesmo tempo (nem dois laços)

  async function perguntar() {
    if (perguntando) return;
    perguntando = true;
    clearTimeout(proximaPergunta);
    try {
      const resposta = await fetch(urlRecebida, { credentials: "same-origin", cache: "no-store" });
      // Login vencido (foi redirecionado para a tela de login) ou sem acesso: para de perguntar
      // (perguntando fica true de propósito, para nada recomeçar o laço).
      if (resposta.redirected || resposta.status === 403) return;
      if (resposta.ok) {
        const { chamada } = await resposta.json();
        if (chamada && !ignoradas.has(chamada.id)) {
          mostrarChamada(chamada);
        } else {
          esconderChamada(); // ninguém chamando, ou já atendida/recusada em outra aba
        }
      }
    } catch (erro) {
      // portal fora do ar ou sem internet: tenta de novo na próxima
    }
    perguntando = false;
    const intervalo = document.hidden ? INTERVALO_EM_SEGUNDO_PLANO : INTERVALO_COM_A_ABA_ABERTA;
    proximaPergunta = setTimeout(perguntar, intervalo);
  }

  // Voltou para a aba: pergunta na hora, sem esperar o intervalo.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) perguntar();
  });

  perguntar();
}

// --- Sino de notificações ---
// O <details> já abre e fecha sozinho; aqui ele também fecha ao clicar fora ou apertar Esc.
const sino = document.querySelector("details[data-sino]");
if (sino) {
  document.addEventListener("click", (evento) => {
    if (sino.open && !sino.contains(evento.target)) sino.open = false;
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && sino.open) {
      sino.open = false;
      sino.querySelector("summary").focus();
    }
  });
}
