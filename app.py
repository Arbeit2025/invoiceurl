"""請求書URL共有メーカー invoiceurl

請求書のデータをサーバーに保存せず、URL のフラグメント（#以降）に
base64url 化した JSON として埋め込んで共有するツール。
フラグメントはサーバーへ送信されないため、請求書データが
サーバー側に残ることは一切ない。
単一ファイル Flask（DB なし）。
"""
import base64
import json
import os

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)


def encode_payload(data):
    """dict を UTF-8 JSON → base64url（パディングなし）の文字列にする。"""
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_payload(s):
    """encode_payload の逆変換。"""
    s = (s or "").strip()
    pad = "=" * (-len(s) % 4)
    raw = base64.urlsafe_b64decode(s + pad)
    return json.loads(raw.decode("utf-8"))


# ページ内 JS と Python で同じ方式（UTF-8 JSON の base64url）を使う。
JS_CODEC = """
function encodePayload(obj){
  const bytes = new TextEncoder().encode(JSON.stringify(obj));
  let bin = "";
  bytes.forEach(function(b){ bin += String.fromCharCode(b); });
  return btoa(bin).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
}
function decodePayload(s){
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) { s += "="; }
  const bin = atob(s);
  const bytes = Uint8Array.from(bin, function(c){ return c.charCodeAt(0); });
  return JSON.parse(new TextDecoder().decode(bytes));
}
"""

FORM_PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>請求書URL共有メーカー</title>
<style>body{font-family:sans-serif;max-width:720px;margin:2em auto;padding:0 1em}
textarea{width:100%}input{margin:.2em}.note{background:#eef6ee;border:1px solid #7a7;padding:.5em 1em;border-radius:8px}
#linkbox{display:none;margin-top:1em}code{word-break:break-all}</style>
</head><body>
<h1>請求書URL共有メーカー</h1>
<div class="note">
<p><strong>データはURLの中だけに保存されます。</strong>入力した請求書データはサーバーに保存されません。「共有リンクを作成」を押すと、データ全体を埋め込んだリンク（<code>/view#…</code>）が作られます。リンクを受け取った人が開くと請求書が表示されます。リンク自体がデータそのものなので、取り扱いにはご注意ください。</p>
</div>

<form id="invform" onsubmit="return makeLink(event)">
  <h2>発行者</h2>
  <label>発行者名 <input type="text" id="issuer" size="40" required></label><br>
  <label>発行者の住所など<br><textarea id="issuer_addr" rows="2" placeholder="〒000-0000 ○○県○○市…"></textarea></label>
  <h2>請求先・日付</h2>
  <label>請求先名 <input type="text" id="client" size="40" required></label><br>
  <label>請求日 <input type="date" id="inv_date"></label>
  <label>支払期限 <input type="date" id="due_date"></label>
  <label>消費税率
    <select id="tax_rate"><option value="10">10%</option><option value="8">8%</option></select></label>
  <h2>品目</h2>
  <p>1行に1品目、「品名,数量,単価」の形式で書いてください（例：<code>デザイン料,1,50000</code>）。</p>
  <textarea id="items" rows="6" placeholder="品名,数量,単価"></textarea><br>
  <button type="submit">共有リンクを作成</button>
</form>

<div id="linkbox">
  <h2>共有リンク</h2>
  <p><a id="sharelink" href="#" target="_blank" rel="noopener"></a></p>
  <input type="text" id="linktext" readonly size="70">
  <button type="button" onclick="copyLink()">リンクをコピー</button>
</div>

<script>
""" + JS_CODEC + """
function makeLink(ev){
  ev.preventDefault();
  const items = [];
  document.getElementById("items").value.split(/\\n/).forEach(function(line){
    const parts = line.split(/[,，]/).map(function(x){ return x.trim(); });
    if (parts.length >= 3 && parts[0]) {
      items.push({name: parts[0], qty: parseFloat(parts[1]) || 0, price: parseFloat(parts[2]) || 0});
    }
  });
  const data = {
    issuer: document.getElementById("issuer").value,
    issuer_addr: document.getElementById("issuer_addr").value,
    client: document.getElementById("client").value,
    inv_date: document.getElementById("inv_date").value,
    due_date: document.getElementById("due_date").value,
    tax_rate: parseInt(document.getElementById("tax_rate").value, 10),
    items: items
  };
  const url = "/view#" + encodePayload(data);
  const a = document.getElementById("sharelink");
  a.href = url; a.textContent = location.origin + url;
  document.getElementById("linktext").value = location.origin + url;
  document.getElementById("linkbox").style.display = "block";
  return false;
}
function copyLink(){
  const t = document.getElementById("linktext");
  t.select();
  if (navigator.clipboard) { navigator.clipboard.writeText(t.value); }
}
</script>
</body></html>"""

VIEW_PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>請求書</title>
<style>body{font-family:sans-serif;max-width:720px;margin:2em auto;padding:0 1em}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #999;padding:.4em .6em}
.num{text-align:right}.total{font-size:1.2em;font-weight:bold}
@media print{ .noprint{display:none} }</style>
</head><body>
<div class="noprint"><button onclick="window.print()">印刷する</button>
<p>この請求書はURLに埋め込まれたデータから表示しています（サーバーには保存されていません）。</p></div>
<div id="invoice"><p>データを読み込んでいます…</p></div>
<script>
""" + JS_CODEC + """
function yen(n){ return n.toLocaleString("ja-JP") + " 円"; }
function render(){
  const box = document.getElementById("invoice");
  let data;
  try {
    data = decodePayload(location.hash.slice(1));
  } catch (e) {
    box.innerHTML = "<p>請求書データを読み取れませんでした。リンクが壊れている可能性があります。</p>";
    return;
  }
  let subtotal = 0;
  let rows = "";
  (data.items || []).forEach(function(it){
    const amount = Math.round((it.qty || 0) * (it.price || 0));
    subtotal += amount;
    rows += "<tr><td>" + escapeHtml(it.name) + "</td><td class='num'>" + it.qty +
            "</td><td class='num'>" + yen(it.price || 0) + "</td><td class='num'>" + yen(amount) + "</td></tr>";
  });
  const tax = Math.floor(subtotal * (data.tax_rate || 10) / 100);
  const total = subtotal + tax;
  box.innerHTML =
    "<h1>請求書</h1>" +
    "<p>請求先：" + escapeHtml(data.client || "") + " 様</p>" +
    "<p>請求日：" + escapeHtml(data.inv_date || "") + "／支払期限：" + escapeHtml(data.due_date || "") + "</p>" +
    "<table><tr><th>品名</th><th>数量</th><th>単価</th><th>金額</th></tr>" + rows + "</table>" +
    "<p>小計：" + yen(subtotal) + "<br>消費税（" + (data.tax_rate || 10) + "%）：" + yen(tax) +
    "<br><span class='total'>合計：" + yen(total) + "</span></p>" +
    "<h2>発行者</h2><p>" + escapeHtml(data.issuer || "") + "<br>" +
    escapeHtml(data.issuer_addr || "").replace(/\\n/g, "<br>") + "</p>";
}
function escapeHtml(s){
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
render();
</script>
</body></html>"""


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template_string(FORM_PAGE)


@app.route("/view")
def view():
    return render_template_string(VIEW_PAGE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
