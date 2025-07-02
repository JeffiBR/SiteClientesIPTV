// Clients page JavaScript functionality

// Delete confirmation modal
function confirmDelete(clientId, clientName) {
    const modal = new bootstrap.Modal(document.getElementById('deleteModal'));
    const clientNameElement = document.getElementById('clientName');
    const deleteForm = document.getElementById('deleteForm');

    // Set client name in modal
    clientNameElement.textContent = clientName;
    
    // Set form action
    deleteForm.action = `/clients/delete/${clientId}`;

    // Show modal
    modal.show();
}

// Form validation
function validateClientForm() {
    const form = document.querySelector('form');
    if (!form) return;

    form.addEventListener('submit', function(event) {
        let isValid = true;

        // Validate required fields
        const requiredFields = form.querySelectorAll('[required]');
        requiredFields.forEach(field => {
            if (!field.value.trim()) {
                field.classList.add('is-invalid');
                isValid = false;
            } else {
                field.classList.remove('is-invalid');
                field.classList.add('is-valid');
            }
        });

        // Validate phone number format
        const phoneField = form.querySelector('[name="phone"]');
        if (phoneField && phoneField.value) {
            const phoneRegex = /^\d{10,15}$/;
            if (!phoneRegex.test(phoneField.value.replace(/\D/g, ''))) {
                phoneField.classList.add('is-invalid');
                showFieldError(phoneField, 'Formato de telefone inválido');
                isValid = false;
            } else {
                phoneField.classList.remove('is-invalid');
                phoneField.classList.add('is-valid');
            }
        }

        // Validate payment value
        const valueField = form.querySelector('[name="value"]');
        if (valueField && valueField.value) {
            const value = parseFloat(valueField.value);
            if (value <= 0) {
                valueField.classList.add('is-invalid');
                showFieldError(valueField, 'Valor deve ser maior que zero');
                isValid = false;
            } else {
                valueField.classList.remove('is-invalid');
                valueField.classList.add('is-valid');
            }
        }

        // Validate payment day
        const paymentDayField = form.querySelector('[name="payment_day"]');
        if (paymentDayField && paymentDayField.value) {
            const day = parseInt(paymentDayField.value);
            if (day < 1 || day > 31) {
                paymentDayField.classList.add('is-invalid');
                showFieldError(paymentDayField, 'Dia deve estar entre 1 e 31');
                isValid = false;
            } else {
                paymentDayField.classList.remove('is-invalid');
                paymentDayField.classList.add('is-valid');
            }
        }

        if (!isValid) {
            event.preventDefault();
            event.stopPropagation();
        }

        form.classList.add('was-validated');
    });
}

function showFieldError(field, message) {
    // Remove existing error message
    const existingError = field.parentElement.querySelector('.invalid-feedback');
    if (existingError) {
        existingError.remove();
    }

    // Add new error message
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;
    field.parentElement.appendChild(errorDiv);
}

// Format phone number input
function formatPhoneInput() {
    const phoneField = document.querySelector('[name="phone"]');
    if (phoneField) {
        phoneField.addEventListener('input', function(e) {
            // Remove all non-digits
            let value = e.target.value.replace(/\D/g, '');
            
            // Limit to 15 digits (international format)
            value = value.substring(0, 15);
            
            e.target.value = value;
        });

        phoneField.addEventListener('blur', function(e) {
            const value = e.target.value;
            if (value && value.length < 10) {
                e.target.classList.add('is-invalid');
                showFieldError(e.target, 'Número muito curto');
            }
        });
    }
}

// Format currency input
function formatCurrencyInput() {
    const valueField = document.querySelector('[name="value"]');
    if (valueField) {
        valueField.addEventListener('blur', function(e) {
            const value = parseFloat(e.target.value);
            if (!isNaN(value)) {
                e.target.value = value.toFixed(2);
            }
        });
    }
}

// Client search functionality
function initializeClientSearch() {
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'form-control mb-3';
    searchInput.placeholder = 'Buscar cliente...';
    searchInput.id = 'clientSearch';

    const table = document.getElementById('clientsTable');
    if (table) {
        table.parentElement.insertBefore(searchInput, table);

        searchInput.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const rows = table.querySelectorAll('tbody tr');

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }
}

// Sort table functionality
function initializeTableSort() {
    const table = document.getElementById('clientsTable');
    if (!table) return;

    const headers = table.querySelectorAll('thead th');
    headers.forEach((header, index) => {
        if (index < headers.length - 1) { // Skip actions column
            header.style.cursor = 'pointer';
            header.addEventListener('click', function() {
                sortTable(table, index);
            });

            // Add sort indicator
            const sortIcon = document.createElement('i');
            sortIcon.className = 'bi bi-arrow-down-up ms-1';
            header.appendChild(sortIcon);
        }
    });
}

function sortTable(table, columnIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const isAscending = table.dataset.sortOrder !== 'asc';
    table.dataset.sortOrder = isAscending ? 'asc' : 'desc';

    rows.sort((a, b) => {
        const aText = a.cells[columnIndex].textContent.trim();
        const bText = b.cells[columnIndex].textContent.trim();

        // Handle numeric columns
        if (columnIndex === 2 || columnIndex === 3) { // Value or payment day
            const aNum = parseFloat(aText.replace(/[^\d.-]/g, ''));
            const bNum = parseFloat(bText.replace(/[^\d.-]/g, ''));
            return isAscending ? aNum - bNum : bNum - aNum;
        }

        // Handle text columns
        return isAscending ? 
            aText.localeCompare(bText) : 
            bText.localeCompare(aText);
    });

    // Re-append sorted rows
    rows.forEach(row => tbody.appendChild(row));

    // Update sort indicators
    const headers = table.querySelectorAll('thead th i');
    headers.forEach(icon => {
        icon.className = 'bi bi-arrow-down-up ms-1';
    });

    const currentHeader = table.querySelectorAll('thead th')[columnIndex].querySelector('i');
    currentHeader.className = isAscending ? 
        'bi bi-arrow-up ms-1' : 
        'bi bi-arrow-down ms-1';
}

// Initialize page functionality
document.addEventListener('DOMContentLoaded', function() {
    validateClientForm();
    formatPhoneInput();
    formatCurrencyInput();
    initializeClientSearch();
    initializeTableSort();

    // Add smooth animations
    const rows = document.querySelectorAll('tbody tr');
    rows.forEach((row, index) => {
        row.style.opacity = '0';
        row.style.transform = 'translateX(-20px)';
        
        setTimeout(() => {
            row.style.transition = 'all 0.3s ease';
            row.style.opacity = '1';
            row.style.transform = 'translateX(0)';
        }, index * 50);
    });
});

// Export clients data
function exportClients() {
    const table = document.getElementById('clientsTable');
    if (!table) return;

    const data = [];
    const headers = Array.from(table.querySelectorAll('thead th'))
        .slice(0, -1) // Remove actions column
        .map(th => th.textContent.trim());

    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const rowData = {};
        const cells = row.querySelectorAll('td');
        
        headers.forEach((header, index) => {
            if (cells[index]) {
                rowData[header] = cells[index].textContent.trim();
            }
        });
        
        data.push(rowData);
    });

    // Create CSV content
    const csvContent = [
        headers.join(','),
        ...data.map(row => headers.map(header => `"${row[header] || ''}"`).join(','))
    ].join('\n');

    // Download CSV
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `clientes-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
}

// Bulk actions (future feature)
function initializeBulkActions() {
    const table = document.getElementById('clientsTable');
    if (!table) return;

    // Add checkboxes to each row
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'form-check-input';
        
        const cell = document.createElement('td');
        cell.appendChild(checkbox);
        row.insertBefore(cell, row.firstChild);
    });

    // Add header checkbox
    const headerRow = table.querySelector('thead tr');
    const headerCheckbox = document.createElement('input');
    headerCheckbox.type = 'checkbox';
    headerCheckbox.className = 'form-check-input';
    
    const headerCell = document.createElement('th');
    headerCell.appendChild(headerCheckbox);
    headerRow.insertBefore(headerCell, headerRow.firstChild);

    // Select all functionality
    headerCheckbox.addEventListener('change', function() {
        const checkboxes = table.querySelectorAll('tbody input[type="checkbox"]');
        checkboxes.forEach(cb => cb.checked = this.checked);
    });
}
