// Comportamentos das telas: ícones, barra lateral, mostrar senha e botão "carregando".

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
