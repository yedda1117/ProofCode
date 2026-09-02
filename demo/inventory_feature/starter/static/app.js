async function loadInventory() {
  const response = await fetch('/api/inventory');
  const data = await response.json();
  document.querySelector('#summary').textContent = `${data.products.length} 件商品`;
  document.querySelector('#inventory-body').innerHTML = data.products.map(product => `
    <tr><td><strong>${product.sku}</strong></td><td>${product.name}</td><td>${product.category}</td><td>${product.stock}</td><td>${product.reorder_level}</td></tr>
  `).join('');
}
loadInventory();
