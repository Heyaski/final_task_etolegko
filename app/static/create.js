const form = document.getElementById("create-form");
const search = document.getElementById("offer-search");
const list = document.getElementById("offer-list");
const picked = document.getElementById("offer-picked");
const offerId = document.getElementById("offer-id");
const error = document.getElementById("form-error");
const result = document.getElementById("result");
const setup = document.getElementById("setup");

let timer = 0;

function showError(message) {
  error.hidden = !message;
  error.textContent = message || "";
}

async function loadSetup() {
  const response = await fetch("/api/setup");
  const body = await response.json();
  if (!response.ok) {
    setup.textContent = body.detail || "Не вижу Keitaro";
    return;
  }
  const bit = (label, item) => (item ? `${label} ${item.name} (#${item.id})` : `${label} не найден`);
  setup.textContent = [
    body.mock ? "Демо-данные." : "Боевой трекер.",
    bit("домен", body.domain),
    bit("группа", body.group),
    bit("источник", body.source),
  ].join(" ");
}

function choose(offer) {
  offerId.value = offer.id;
  picked.textContent = `[${offer.id}] ${offer.name}`;
  search.value = offer.name;
  list.hidden = true;
}

async function lookup() {
  const q = search.value.trim();
  if (/^\d+$/.test(q)) offerId.value = q;
  const response = await fetch("/api/offers?q=" + encodeURIComponent(q));
  const offers = await response.json();
  list.innerHTML = "";
  if (!response.ok || !offers.length) {
    list.hidden = true;
    return;
  }
  for (const offer of offers) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `[${offer.id}] ${offer.name}`;
    button.addEventListener("click", () => choose(offer));
    item.appendChild(button);
    list.appendChild(item);
  }
  list.hidden = false;
}

search.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(lookup, 180);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  const payload = {
    name: form.name.value,
    geo: form.geo.value,
    offer_id: Number(offerId.value || search.value),
  };
  if (!payload.offer_id) {
    showError("Выберите оффер из списка или введите его ID");
    return;
  }
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  const response = await fetch("/api/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  button.disabled = false;
  if (!response.ok) {
    showError(body.detail || "Не удалось создать кампанию");
    return;
  }
  const esc = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  result.innerHTML = `
    <h2>${esc(body.name)}</h2>
    <p>ID <span class="num">${body.id}</span>, алиас <span class="num">${esc(body.alias)}</span></p>
    <p><a href="${esc(body.url)}" target="_blank" rel="noreferrer">${esc(body.url)}</a></p>
    <p>Flow 1: ${esc(body.geos.join(", "))} на Google</p>
    <p>Flow 2: [${body.offer.id}] ${esc(body.offer.name)}</p>
    <p>Домен ${esc(body.domain.name)}, группа ${esc(body.group.name)}, источник ${esc(body.source.name)}</p>
    <p><a href="/campaigns/${body.id}">Открыть</a> <a href="${esc(body.admin_url)}" target="_blank" rel="noreferrer">Keitaro</a></p>`;
});

loadSetup();
