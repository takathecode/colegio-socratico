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
      linha.classList.add("bg-[#EAF0F8]");
      linha.scrollIntoView({ block: "nearest", behavior: "smooth" });
      await esperar(TEMPO_DE_LEITURA);

      if (Math.random() < CHANCE_DE_RECONHECER) {
        marcar(linha, "presente", "BIOMETRIA");
        reconhecidos += 1;
      } else {
        marcar(linha, "falta", "MANUAL");
      }
      linha.classList.remove("bg-[#EAF0F8]");
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
