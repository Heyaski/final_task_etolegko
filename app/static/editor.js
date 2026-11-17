const boot = JSON.parse(document.getElementById("boot").textContent);
const root = document.getElementById("streams");
const errorNode = document.getElementById("editor-error");
let campaign = boot;
const snapshots = new Map();

function showError(message) {
  errorNode.hidden = !message;
  errorNode.textContent = message || "";
}

function snapshot(stream) {
  snapshots.set(stream.id, JSON.stringify(stream.offers));
}

function dirty(stream) {
  return snapshots.get(stream.id) !== JSON.stringify(stream.offers);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function render() {
  root.innerHTML = "";
  for (const stream of campaign.streams) {
    const section = document.createElement("section");
    section.className = "stream" + (dirty(stream) ? " dirty" : "");
    const activeSum = stream.offers.filter((row) => !row.removed).reduce((sum, row) => sum + Number(row.share || 0), 0);
    const filters = (stream.filters || []).join(", ");
    const target = stream.action_payload ? `<div class="meta">${escapeHtml(stream.action_payload)}</div>` : "";
    section.innerHTML = `
      <div class="stream-head">
        <div>
          <strong>${escapeHtml(stream.name)}</strong>
          <span class="num"> #${stream.id}</span>
          <div class="meta">${filters ? escapeHtml(filters) + ". " : ""}<span data-clicks="${stream.id}"></span></div>
          ${target}
        </div>
        <div></div><div></div><div></div>
        <div class="actions">
          ${dirty(stream) ? `<button type="button" data-push="${stream.id}" class="primary">Отправить в Keitaro</button><button type="button" data-cancel="${stream.id}">Отмена</button>` : ""}
        </div>
      </div>
      <div class="cols"><span>Оффер</span><span>Доля</span><span>Сегодня</span><span>7 дней</span><span></span></div>`;
    for (const row of stream.offers) {
      const article = document.createElement("article");
      article.className = "offer" + (row.removed ? " removed" : "");
      const preview = row.url ? `<a href="${escapeHtml(row.url)}" target="_blank" rel="noreferrer">превью</a>` : "";
      article.innerHTML = `
        <div>${escapeHtml(row.name)} <div class="meta">#${row.offer_id} ${row.removed ? "снят" : ""} ${preview}</div></div>
        <div class="share">
          <button type="button" data-nudge="-1" data-offer="${row.offer_id}" data-stream="${stream.id}" ${row.removed ? "disabled" : ""}>−</button>
          <b class="num">${row.share}%</b>
          <button type="button" data-nudge="1" data-offer="${row.offer_id}" data-stream="${stream.id}" ${row.removed ? "disabled" : ""}>+</button>
        </div>
        <div class="num" data-stat="${row.offer_id}">—</div>
        <div class="bars" data-trend="${row.offer_id}"></div>
        <div>${row.removed
          ? `<button type="button" data-restore="${row.offer_id}" data-stream="${stream.id}">Вернуть</button>`
          : `<button type="button" class="danger" data-remove="${row.offer_id}" data-stream="${stream.id}">Удалить</button>`}</div>`;
      section.appendChild(article);
    }
    const footer = document.createElement("div");
    if (stream.offers.length) {
      footer.className = "sum" + (activeSum === 100 ? "" : " bad");
      footer.innerHTML = `Сумма долей: <b class="num">${activeSum}%</b>` + (activeSum === 100 ? "" : ` <button type="button" class="tiny" data-equalize="${stream.id}">Уравнять</button>`);
    }
    const adder = document.createElement("div");
    adder.className = "sum";
    adder.innerHTML = `<input data-add-search="${stream.id}" placeholder="добавить оффер"><ul class="suggest" data-add-list="${stream.id}" hidden></ul>`;
    section.append(footer, adder);
    root.appendChild(section);
  }
}

async function mutate(stream, op, extra) {
  showError("");
  const response = await fetch("/api/shares", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ op, rows: stream.offers, ...extra }),
  });
  const body = await response.json();
  if (!response.ok) {
    showError(body.detail || "Не получилось пересчитать доли");
    return;
  }
  stream.offers = body.rows;
  render();
  paintStats();
}

function streamById(id) {
  return campaign.streams.find((item) => String(item.id) === String(id));
}

root.addEventListener("click", async (event) => {
  const target = event.target.closest("button");
  if (!target) return;
  const stream = streamById(target.dataset.stream || target.dataset.push || target.dataset.cancel || target.dataset.equalize);
  if (target.dataset.push) {
    await push(streamById(target.dataset.push));
    return;
  }
  if (target.dataset.cancel) {
    const current = streamById(target.dataset.cancel);
    current.offers = JSON.parse(snapshots.get(current.id));
    render();
    paintStats();
    return;
  }
  if (target.dataset.equalize) {
    await mutate(stream, "equalize");
    return;
  }
  if (target.dataset.remove) {
    await mutate(stream, "remove", { offer_id: Number(target.dataset.remove) });
    return;
  }
  if (target.dataset.restore) {
    await mutate(stream, "restore", { offer_id: Number(target.dataset.restore) });
    return;
  }
  if (target.dataset.nudge) {
    await mutate(stream, "nudge", { offer_id: Number(target.dataset.offer), delta: Number(target.dataset.nudge) });
  }
});

root.addEventListener("input", (event) => {
  const input = event.target;
  if (!input.dataset.addSearch) return;
  clearTimeout(input._timer);
  input._timer = setTimeout(() => suggest(input), 180);
});

async function suggest(input) {
  const list = root.querySelector(`[data-add-list="${input.dataset.addSearch}"]`);
  const response = await fetch("/api/offers?q=" + encodeURIComponent(input.value.trim()));
  const offers = await response.json();
  list.innerHTML = "";
  list.hidden = !offers.length;
  for (const offer of offers) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `[${offer.id}] ${offer.name}`;
    button.addEventListener("click", async () => {
      await mutate(streamById(input.dataset.addSearch), "add", { offer });
      input.value = "";
      list.hidden = true;
    });
    item.appendChild(button);
    list.appendChild(item);
  }
}

async function push(stream) {
  showError("");
  const button = root.querySelector(`[data-push="${stream.id}"]`);
  button.disabled = true;
  const response = await fetch(`/api/campaigns/${campaign.id}/streams/${stream.id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ offers: stream.offers }),
  });
  const body = await response.json();
  if (!response.ok) {
    showError(body.detail || "Keitaro не принял поток");
    button.disabled = false;
    return;
  }
  await reload();
}

async function reload() {
  const response = await fetch(`/api/campaigns/${campaign.id}`);
  const body = await response.json();
  if (!response.ok) {
    showError(body.detail || "Не удалось забрать потоки");
    return;
  }
  campaign = body;
  for (const stream of campaign.streams) snapshot(stream);
  render();
  loadStats();
}

document.getElementById("fetch").addEventListener("click", reload);

const dialog = document.getElementById("offer-dialog");
const dialogSearch = document.getElementById("dialog-search");
const dialogList = document.getElementById("dialog-list");
const targetStream = document.getElementById("target-stream");

document.getElementById("all-offers").addEventListener("click", async () => {
  targetStream.innerHTML = campaign.streams.map((stream) => `<option value="${stream.id}">${escapeHtml(stream.name)}</option>`).join("");
  dialog.showModal();
  await fillDialog("");
});

dialogSearch.addEventListener("input", () => {
  clearTimeout(dialogSearch._timer);
  dialogSearch._timer = setTimeout(() => fillDialog(dialogSearch.value.trim()), 180);
});

async function fillDialog(query) {
  const response = await fetch("/api/offers?q=" + encodeURIComponent(query) + "&limit=50");
  const offers = await response.json();
  dialogList.innerHTML = "";
  for (const offer of offers) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `[${offer.id}] ${offer.name}`;
    button.addEventListener("click", async () => {
      await mutate(streamById(targetStream.value), "add", { offer });
      dialog.close();
    });
    item.appendChild(button);
    dialogList.appendChild(item);
  }
}

let stats = null;

async function loadStats() {
  const response = await fetch(`/api/campaigns/${campaign.id}/stats`);
  stats = await response.json();
  paintStats();
}

function paintStats() {
  if (!stats) return;
  if (!stats.ok) {
    showError(stats.error || "Статистика недоступна");
    return;
  }
  for (const [streamId, clicks] of Object.entries(stats.streams || {})) {
    const node = root.querySelector(`[data-clicks="${streamId}"]`);
    if (node) node.textContent = `клики сегодня: ${clicks}`;
  }
  for (const node of root.querySelectorAll("[data-stat]")) {
    const row = (stats.offers || {})[node.dataset.stat];
    node.textContent = row ? `${row.clicks} кл, ${row.unique} ун, ${row.conversions} конв, ${Number(row.revenue).toFixed(2)}` : "0 кл";
  }
  for (const node of root.querySelectorAll("[data-trend]")) {
    const row = (stats.offers || {})[node.dataset.trend];
    const series = row ? row.trend : [0, 0, 0, 0, 0, 0, 0];
    const max = Math.max(1, ...series);
    node.innerHTML = series.map((value) => `<i style="height:${Math.max(2, (value / max) * 36)}px" title="${value}"></i>`).join("");
  }
}

for (const stream of campaign.streams) snapshot(stream);
render();
loadStats();
