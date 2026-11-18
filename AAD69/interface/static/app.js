// Interface AAD69 : le peu de JavaScript nécessaire.
// 1) ouvrir / fermer le panneau des réglages ; 2) recalculer dès qu'on change un menu marqué data-auto.
const tailleTexteCle = "aad69-taille-texte";
const taillesTexte = ["small", "standard", "large"];
const tailleTexteEnregistree = localStorage.getItem(tailleTexteCle);
if (taillesTexte.includes(tailleTexteEnregistree)) {
  document.documentElement.dataset.tailleTexte = tailleTexteEnregistree;
  document.querySelector(`input[name="taille-texte"][value="${tailleTexteEnregistree}"]`).checked = true;
}

const formulaireTextes = document.querySelector("[data-form-textes]");
if (formulaireTextes) {
  const cartes = formulaireTextes.querySelector("[data-cartes-discours]");
  const boutonAjouter = formulaireTextes.querySelector("[data-ajouter-discours]");
  const modeleCarte = formulaireTextes.querySelector("[data-modele-carte-discours]");
  const lienSansJavaScript = formulaireTextes.querySelector(".ajout-sans-js");

  const compter = (carte) => {
    const texte = carte.querySelector("textarea").value;
    const phrases = (texte.match(/[^.!?…]+(?:[.!?…]+|$)/g) || []).filter((phrase) => phrase.trim()).length;
    const mots = texte.trim() ? texte.trim().split(/\s+/).length : 0;
    const sortie = carte.querySelector("[data-compteurs]");
    sortie.textContent = `${phrases} phrases · ${mots} mots`;
    sortie.hidden = false;
  };
  const numeroter = () => {
    cartes.querySelectorAll("[data-carte-discours]").forEach((carte, index) => {
      carte.querySelector("[data-titre-carte]").textContent = `Discours ${index + 1}`;
      const nom = carte.querySelector("input[name='nom']");
      if (!nom.dataset.modifie) nom.value = `discours-${index + 1}`;
      carte.querySelector("textarea").setAttribute("aria-label", `Texte du discours ${index + 1}`);
      compter(carte);
    });
  };

  cartes.replaceChildren();
  lienSansJavaScript.hidden = true;
  boutonAjouter.hidden = false;

  boutonAjouter.addEventListener("click", () => {
    const numero = cartes.querySelectorAll("[data-carte-discours]").length + 1;
    const carte = modeleCarte.content.firstElementChild.cloneNode(true);
    carte.innerHTML = carte.innerHTML.replaceAll("__NUMERO__", String(numero));
    carte.querySelector("[data-retirer-discours]").hidden = false;
    cartes.append(carte);
    numeroter();
    carte.querySelector("input[name='nom']").focus();
  });
  cartes.addEventListener("input", (event) => {
    if (event.target.matches("textarea")) compter(event.target.closest("[data-carte-discours]"));
    if (event.target.matches("input[name='nom']")) event.target.dataset.modifie = "true";
  });
  cartes.addEventListener("click", (event) => {
    const retirer = event.target.closest("[data-retirer-discours]");
    if (!retirer) return;
    retirer.closest("[data-carte-discours]").remove();
    numeroter();
  });
}

document.addEventListener("click", (e) => {
  const ouvre = e.target.closest("[data-ouvre]");
  if (ouvre) document.getElementById(ouvre.dataset.ouvre).showModal();
  const ferme = e.target.closest("[data-ferme]");
  if (ferme) document.getElementById(ferme.dataset.ferme).close();
});
document.addEventListener("change", (e) => {
  if (e.target.matches("input[name='taille-texte']")) {
    document.documentElement.dataset.tailleTexte = e.target.value;
    localStorage.setItem(tailleTexteCle, e.target.value);
  }
  if (e.target.matches("select[data-auto]")) e.target.form.submit();
});
document.addEventListener("submit", (e) => {
  const form = e.target;
  const message = form.dataset.loadingMessage;
  if (!message) return;
  form.setAttribute("aria-busy", "true");
  const status = document.getElementById("loading-status");
  if (!status) return;
  status.hidden = false;
  status.textContent = message;
  const bouton = form.querySelector("button[type='submit']");
  if (bouton) {
    bouton.disabled = true;
    bouton.dataset.originalLabel = bouton.textContent;
    bouton.textContent = "Chargement…";
  }
});
document.addEventListener("click", (e) => {
  const vider = e.target.closest("[data-vide-textes]");
  if (!vider) return;
  const formulaire = vider.closest("form");
  formulaire.querySelectorAll("textarea").forEach((champ) => { champ.value = ""; });
  formulaire.querySelectorAll("input[type='file']").forEach((champ) => { champ.value = ""; });
});
// Un clic sur le fond assombri ferme le panneau.
document.querySelectorAll("dialog").forEach((d) =>
  d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));
