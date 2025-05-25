
let cart = {};
let cartCount = 0;
let cartTotal = 0;

function uploadFile() {
    const fileInput = document.getElementById('pdfFile');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a PDF file first!');
        return;
    }
    
    const formData = new FormData();
    formData.append('pdf_file', file);
    
    document.getElementById('uploadSection').style.display = 'none';
    document.getElementById('loadingSection').style.display = 'block';
    
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('loadingSection').style.display = 'none';
        
        
if (data.success) {
    displayMenu(data.menu);
} else {
    document.getElementById('uploadSection').style.display = 'block';
    alert('Error: ' + data.error);
}
})
.catch(error => {
document.getElementById('loadingSection').style.display = 'none';
document.getElementById('uploadSection').style.display = 'block';
alert('Error uploading file: ' + error);
});
}

function displayMenu(menu) {
const menuContent = document.getElementById('menuContent');
let html = '<h2 class="text-center mb-4"><i class="fas fa-utensils"></i> Menu</h2>';

for (const [category, items] of Object.entries(menu)) {
html += `<div class="category-header">
    <i class="fas fa-list"></i> ${category}
</div>`;

items.forEach((item, index) => {
    const itemId = `${category}_${index}`;
    html += `
        <div class="menu-item">
            <div class="row">
                <div class="col-md-8">
                    <div class="item-name">${item.name}</div>
                    <div class="item-desc">${item.desc}</div>
                    <div class="item-price">₹${item.price}</div>
                </div>
                <div class="col-md-4">
                    <div class="quantity-controls">
                        <button class="qty-btn" onclick="changeQuantity('${itemId}', -1)">
                            <i class="fas fa-minus"></i>
                        </button>
                        <div class="qty-display" id="qty_${itemId}">0</div>
                        <button class="qty-btn" onclick="changeQuantity('${itemId}', 1)">
                            <i class="fas fa-plus"></i>
                        </button>
                    </div>
                    <button class="add-to-cart" onclick="addToCart('${itemId}', '${item.name}', ${item.price})">
                        <i class="fas fa-cart-plus"></i> Add to Cart
                    </button>
                </div>
            </div>
        </div>
    `;
});
}

menuContent.innerHTML = html;
document.getElementById('menuSection').style.display = 'block';
document.getElementById('cartToggle').style.display = 'flex';
}

function changeQuantity(itemId, change) {
const qtyElement = document.getElementById(`qty_${itemId}`);
let currentQty = parseInt(qtyElement.textContent);
currentQty = Math.max(0, currentQty + change);
qtyElement.textContent = currentQty;
}

function addToCart(itemId, itemName, itemPrice) {
const qtyElement = document.getElementById(`qty_${itemId}`);
const quantity = parseInt(qtyElement.textContent);

if (quantity === 0) {
alert('Please select quantity first!');
return;
}

if (cart[itemId]) {
cart[itemId].quantity += quantity;
} else {
cart[itemId] = {
    name: itemName,
    price: itemPrice,
    quantity: quantity
};
}

qtyElement.textContent = '0';
updateCartDisplay();
}

function updateCartDisplay() {
cartCount = 0;
cartTotal = 0;
let cartHtml = '';

for (const [itemId, item] of Object.entries(cart)) {
cartCount += item.quantity;
cartTotal += item.price * item.quantity;

cartHtml += `
    <div class="cart-item">
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <div class="fw-bold">${item.name}</div>
                <div class="text-muted">₹${item.price} × ${item.quantity}</div>
            </div>
            <div>
                <button class="btn btn-sm btn-outline-danger" onclick="removeFromCart('${itemId}')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    </div>
`;
}

if (cartCount === 0) {
cartHtml = '<div class="cart-item text-center text-muted">Your cart is empty</div>';
}

document.getElementById('cartItems').innerHTML = cartHtml;
document.getElementById('cartTotal').innerHTML = `Total: ₹${cartTotal}`;
document.getElementById('cartBadge').textContent = cartCount;
}

function removeFromCart(itemId) {
delete cart[itemId];
updateCartDisplay();
}

function toggleCart() {
const cartSidebar = document.getElementById('cartSidebar');
cartSidebar.classList.toggle('open');
}

// File input change handler
document.getElementById('pdfFile').addEventListener('change', function(e) {
const fileName = e.target.files[0]?.name;
if (fileName) {
document.querySelector('.upload-area h4').textContent = fileName;
}
});

// Drag and drop functionality
const uploadArea = document.querySelector('.upload-area');

uploadArea.addEventListener('dragover', (e) => {
e.preventDefault();
uploadArea.style.background = 'rgba(255,255,255,0.2)';
});

uploadArea.addEventListener('dragleave', () => {
uploadArea.style.background = 'transparent';
});

uploadArea.addEventListener('drop', (e) => {
e.preventDefault();
uploadArea.style.background = 'transparent';

const files = e.dataTransfer.files;
if (files.length > 0 && files[0].type === 'application/pdf') {
document.getElementById('pdfFile').files = files;
document.querySelector('.upload-area h4').textContent = files[0].name;
}
});