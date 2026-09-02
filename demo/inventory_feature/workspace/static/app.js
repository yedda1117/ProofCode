let products = [];
let activeFilter = 'all';
let pendingCsv = '';

function risk(product) {
  if (product.stock <= 0) return 'out';
  if (product.stock < product.reorder_level) return 'low';
  return 'normal';
}

function riskLabel(status) {
  return { out: '缺货', low: '低库存', normal: '正常' }[status] || status;
}

function renderStats() {
  const counts = { out: 0, low: 0, normal: 0 };
  products.forEach(p => { counts[risk(p)] += 1; });
  document.querySelector('#stat-total').textContent = products.length;
  document.querySelector('#stat-out').textContent = counts.out;
  document.querySelector('#stat-low').textContent = counts.low;
  document.querySelector('#stat-normal').textContent = counts.normal;
  document.querySelector('#summary').textContent = `${products.length} 件商品`;
}

function renderTable() {
  const filtered = activeFilter === 'all'
    ? products
    : products.filter(p => risk(p) === activeFilter);
  document.querySelector('#list-summary').textContent =
    activeFilter === 'all'
      ? `共 ${filtered.length} 件商品`
      : `${riskLabel(activeFilter)}：${filtered.length} 件`;
  document.querySelector('#inventory-body').innerHTML = filtered.map(product => `
    <tr class="risk-${risk(product)}">
      <td><strong>${product.sku}</strong></td>
      <td>${product.name}</td>
      <td>${product.category}</td>
      <td>${product.stock}</td>
      <td>${product.reorder_level}</td>
      <td><span class="pill pill-${risk(product)}">${riskLabel(risk(product))}</span></td>
    </tr>
  `).join('') || '<tr><td colspan="6">没有匹配的商品</td></tr>';
}

async function loadInventory() {
  const response = await fetch('/api/inventory');
  const data = await response.json();
  products = data.products;
  renderStats();
  renderTable();
}

function setFeedback(message, kind) {
  const el = document.querySelector('#feedback');
  el.textContent = message;
  el.className = kind ? `feedback feedback-${kind}` : 'feedback';
}

function renderPreview(rows) {
  document.querySelector('#preview-table').innerHTML = rows.map(row => `
    <tr><td><strong>${row.sku}</strong></td><td>${row.name}</td><td>${row.category}</td><td>${row.stock}</td><td>${row.reorder_level}</td></tr>
  `).join('') || '<tr><td colspan="5">没有可导入的行</td></tr>';
}

async function handlePreview() {
  const file = document.querySelector('#csv-input').files[0];
  if (!file) {
    setFeedback('请先选择 CSV 文件。', 'error');
    return;
  }
  pendingCsv = await file.text();
  const response = await fetch('/api/import/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csv: pendingCsv }),
  });
  const result = await response.json();
  renderPreview(result.rows || []);
  const importButton = document.querySelector('#import-button');
  if (result.can_commit) {
    importButton.disabled = false;
    setFeedback(`校验通过，共 ${(result.rows || []).length} 行可导入。`, 'success');
  } else {
    importButton.disabled = true;
    const messages = (result.errors || []).map(e => `第 ${e.row} 行：${e.message}`).join('；');
    setFeedback(`校验未通过，未写入任何数据。${messages}`, 'error');
  }
}

async function handleImport() {
  if (!pendingCsv) return;
  const response = await fetch('/api/import/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csv: pendingCsv }),
  });
  const result = await response.json();
  if (response.ok) {
    setFeedback(`成功导入 ${result.imported} 件商品。`, 'success');
    document.querySelector('#csv-input').value = '';
    document.querySelector('#preview-table').innerHTML = '';
    document.querySelector('#import-button').disabled = true;
    pendingCsv = '';
    await loadInventory();
  } else {
    setFeedback(`导入失败：${result.error || '未知错误'}`, 'error');
  }
}

document.querySelectorAll('#stats .stat').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('#stats .stat').forEach(b => b.classList.remove('active'));
    button.classList.add('active');
    activeFilter = button.dataset.filter;
    renderTable();
  });
});
document.querySelector('#preview-button').addEventListener('click', handlePreview);
document.querySelector('#import-button').addEventListener('click', handleImport);

loadInventory();
