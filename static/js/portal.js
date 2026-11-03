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
