"use strict";
const token = location.hash.slice(1);
const statusNode = document.querySelector("#status");
const exportButton = document.querySelector("#export");
let busy = false;

async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Kicho-Token": token, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "操作に失敗しました。");
  }
  return response;
}

async function download(batchId) {
  const response = await request(`/api/exports/${encodeURIComponent(batchId)}`);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `freee-${batchId}.csv`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function action(work) {
  if (busy) return;
  busy = true;
  document.querySelectorAll("button").forEach(button => { button.disabled = true; });
  try {
    await work();
    await refresh();
  } catch (error) {
    statusNode.textContent = error instanceof Error ? error.message : "操作に失敗しました。";
  } finally {
    busy = false;
    document.querySelector("#refresh").disabled = false;
  }
}

async function refresh() {
  const data = await (await request("/api/queue")).json();
  document.querySelector("#client").textContent = `顧客: ${data.client_id}`;
  const rows = document.querySelector("#rows");
  rows.replaceChildren();
  const readyCount = data.rows.filter(row => row.confirmed && row.can_confirm).length;
  statusNode.textContent = `${data.rows.length}件 / CSV出力対象 ${readyCount}件`;
  exportButton.disabled = readyCount === 0;
  for (const row of data.rows) {
    const article = document.querySelector("#row-template").content.cloneNode(true);
    const deal = row.freee_deal;
    const amountLabel = deal.金額 == null ? "金額不明" : `¥${Number(deal.金額).toLocaleString("ja-JP")}`;
    article.querySelector("h2").textContent = `${deal.発生日 || "日付不明"}　${deal.取引先 || "取引先不明"}　${amountLabel}`;
    article.querySelector(".badge").textContent = row.exported ? "CSV出力済み" : row.action === "suggestion" ? "同期明細への提案" : row.confirmed ? "確定済み" : row.can_confirm ? "確認待ち" : "要確認";
    const display = { ...deal, 決済状態: { paid: "決済済み", unpaid: "未決済", unknown: "未確認" }[row.settlement_status] };
    const fields = ["収支区分", "勘定科目", "税区分", "税計算区分", "税額", "決済状態", "決済日", "決済口座", "決済金額", "決済期日", "品目", "備考"];
    for (const field of fields) {
      const term = document.createElement("dt");
      const value = document.createElement("dd");
      term.textContent = field;
      value.textContent = display[field] === "" || display[field] == null ? "—" : String(display[field]);
      article.querySelector("dl").append(term, value);
    }
    for (const reason of row.reasons) {
      const item = document.createElement("li");
      item.textContent = reason;
      article.querySelector(".reasons").append(item);
    }
    if (row.statement_id) {
      const item = document.createElement("li");
      item.textContent = `明細ID: ${row.statement_id}`;
      article.querySelector(".reasons").append(item);
    }
    article.querySelector(".source").textContent = row.raw_text;
    article.querySelector(".journal").textContent = JSON.stringify(row.journal, null, 2);
    article.querySelector(".answers").textContent = JSON.stringify(row.answers, null, 2);
    const button = article.querySelector(".confirm");
    button.textContent = row.confirmed ? "確定を取り消す" : "この取引を確定";
    button.disabled = !row.can_confirm;
    button.addEventListener("click", () => action(async () => {
      await request(row.confirmed ? "/api/unconfirm" : "/api/confirm", { draft_id: row.draft_id, revision: row.revision });
    }));
    rows.append(article);
  }
  const exportsNode = document.querySelector("#exports");
  exportsNode.replaceChildren();
  for (const batch of data.exports) {
    const button = document.createElement("button");
    button.textContent = `${new Date(batch.created_at).toLocaleString("ja-JP")} / ${batch.count}件を再ダウンロード`;
    button.addEventListener("click", () => action(() => download(batch.batch_id)));
    exportsNode.append(button);
  }
}

document.querySelector("#refresh").addEventListener("click", () => action(async () => {}));
exportButton.addEventListener("click", () => action(async () => {
  const batch = await (await request("/api/export", {})).json();
  await download(batch.batch_id);
}));
action(async () => {});
