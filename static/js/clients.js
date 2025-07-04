// Clients page JavaScript functionality

// Global variables
let currentFilter = 'all';
let searchTerm = '';

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

// Renewal modal functionality
function showRenewalModal(clientId, clientName, clientPlan = '', clientValue = 0) {
    const modal = new bootstrap.Modal(document.getElementById('renewalModal'));
    const clientNameElement = document.getElementById('renewalClientName');
    const clientPlanElement = document.getElementById('renewalClientPlan');
    const clientValueElement = document.getElementById('renewalClientValue');
    const renewalForm = document.getElementById('renewalForm');
    const customDaysInput = document.getElementById('customDaysInput');
    const customDaysField = document.getElementById('custom_days');
    const renewalPreviewText = document.getElementById('renewalPreviewText');

    // Get plan and value from data attributes if not provided
    const button = event.target.closest('button');
    if (button) {
        clientPlan = button.dataset.plan || clientPlan;
        clientValue = button.dataset.value || clientValue;
    }

    // Set client info
    clientNameElement.textContent = clientName;
    clientPlanElement.textContent = clientPlan || 'N/A';
    clientValueElement.textContent = clientValue ? `R$ ${parseFloat(clientValue).toFixed(2)}` : 'R$ 0,00';
    
    // Set form action
    renewalForm.action = `/clients/renew/${clientId}`;

    // Handle renewal days selection
    const renewalDaysRadios = document.querySelectorAll('input[name="renewal_days"]');
    renewalDaysRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.value === 'custom') {
                customDaysInput.style.display = 'block';
                customDaysField.required = true;
                customDaysField.focus();
            } else {
                customDaysInput.style.display = 'none';
                customDaysField.required = false;
                updateRenewalPreview(this.value);
            }
        });
    });

    // Handle custom days input
    customDaysField.addEventListener('input', function() {
        if (this.value && this.value > 0) {
            updateRenewalPreview(this.value);
        }
    });

    // Form submission handling
    renewalForm.onsubmit = function(e) {
        const customRadio = document.getElementById('daysCustom');
        if (customRadio.checked) {
            if (!customDaysField.value || customDaysField.value <= 0) {
                e.preventDefault();
                alert('Por favor, insira um número válido de dias');
                return false;
            }
            // Set the custom value as the renewal_days value
            customRadio.value = customDaysField.value;
        }
    };

    // Initial preview
    updateRenewalPreview(30);

    // Show modal
    modal.show();
}

// Update renewal preview
function updateRenewalPreview(days) {
    const renewalPreviewText = document.getElementById('renewalPreviewText');
    if (renewalPreviewText) {
        const today = new Date();
        const futureDate = new Date(today.getTime() + (days * 24 * 60 * 60 * 1000));
        const formattedDate = futureDate.toLocaleDateString('pt-BR');
        
        let period = '';
        if (days == 30) period = ' (1 mês)';
        else if (days == 60) period = ' (2 meses)';
        else if (days == 90) period = ' (3 meses)';
        else if (days == 180) period = ' (6 meses)';
        else if (days == 365) period = ' (1 ano)';
        
        renewalPreviewText.textContent = `O plano será renovado por ${days} dias${period} até ${formattedDate}`;
    }
}

// Observations modal functionality
function showObservationsModal(clientId, clientName) {
    const modal = new bootstrap.Modal(document.getElementById('observationsModal'));
    const clientNameElement = document.getElementById('observationsClientName');
    const currentObservations = document.getElementById('currentObservations');
    const currentObservationsText = document.getElementById('currentObservationsText');
    const observationsForm = document.getElementById('observationsForm');
    const newObservationField = document.getElementById('new_observation');

    // Get observations from data attribute
    const button = event.target.closest('button');
    const observations = button ? button.dataset.observations : '';

    // Set client name
    clientNameElement.textContent = clientName;
    
    // Set form action
    observationsForm.action = `/clients/observations/${clientId}`;

    // Show/hide current observations
    if (observations && observations.trim()) {
        currentObservations.style.display = 'block';
        currentObservationsText.textContent = observations;
    } else {
        currentObservations.style.display = 'none';
    }

    // Clear new observation field
    newObservationField.value = '';
    newObservationField.focus();

    // Show modal
    modal.show();
}

// Payment status toggle
function togglePaymentStatus(clientId, currentStatus) {
    const form = document.getElementById('paymentStatusForm');
    const statusInput = document.getElementById('paymentStatus');
    
    // Set new status (toggle)
    const newStatus = currentStatus === 'paid' ? 'pending' : 'paid';
    statusInput.value = newStatus;
    
    // Set form action
    form.action = `/clients/payment-status/${clientId}`;
    
    // Submit form
    form.submit();
}

// Mobile filter functionality
function initializeMobileFilters() {
    const tabs = document.querySelectorAll('.mobile-nav-tab');
    const mobileSearch = document.getElementById('mobileClientSearch');
    
    // Tab click handlers
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            // Remove active class from all tabs
            tabs.forEach(t => t.classList.remove('active'));
            
            // Add active class to clicked tab
            this.classList.add('active');
            
            // Update current filter
            currentFilter = this.dataset.filter;
            
            // Apply filters
            applyMobileFilters();
        });
    });
    
    // Mobile search handler
    if (mobileSearch) {
        mobileSearch.addEventListener('input', function() {
            searchTerm = this.value.toLowerCase();
            applyMobileFilters();
        });
    }
}

// Apply mobile filters
function applyMobileFilters() {
    const cards = document.querySelectorAll('.client-card');
    
    cards.forEach(card => {
        const status = card.dataset.status;
        const name = card.dataset.name;
        const phone = card.dataset.phone;
        const plan = card.dataset.plan;
        
        // Check status filter
        const statusMatch = currentFilter === 'all' || status === currentFilter;
        
        // Check search term
        const searchMatch = searchTerm === '' || 
            name.includes(searchTerm) || 
            phone.includes(searchTerm) || 
            plan.toLowerCase().includes(searchTerm);
        
        // Show/hide card
        if (statusMatch && searchMatch) {
            card.style.display = 'block';
            card.classList.add('animate-slide-in');
        } else {
            card.style.display = 'none';
            card.classList.remove('animate-slide-in');
        }
    });
}

// Desktop search and filter
function initializeDesktopFilters() {
    const searchInput = document.getElementById('clientSearch');
    const statusFilter = document.getElementById('statusFilter');
    const planFilter = document.getElementById('planFilter');
    
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            applyDesktopFilters();
        });
    }
    
    if (statusFilter) {
        statusFilter.addEventListener('change', function() {
            applyDesktopFilters();
        });
    }
    
    if (planFilter) {
        planFilter.addEventListener('change', function() {
            applyDesktopFilters();
        });
    }
}

// Apply desktop filters
function applyDesktopFilters() {
    const searchInput = document.getElementById('clientSearch');
    const statusFilter = document.getElementById('statusFilter');
    const planFilter = document.getElementById('planFilter');
    const rows = document.querySelectorAll('#clientsTable tbody tr');
    
    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    const statusValue = statusFilter ? statusFilter.value : '';
    const planValue = planFilter ? planFilter.value : '';
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        const status = row.dataset.status;
        const plan = row.dataset.plan;
        
        const searchMatch = text.includes(searchTerm);
        const statusMatch = statusValue === '' || status === statusValue;
        const planMatch = planValue === '' || plan === planValue;
        
        if (searchMatch && statusMatch && planMatch) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
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
    const phoneFields = document.querySelectorAll('[name="phone"]');
    phoneFields.forEach(phoneField => {
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
    });
}

// Format currency input
function formatCurrencyInput() {
    const valueFields = document.querySelectorAll('[name="value"]');
    valueFields.forEach(valueField => {
        valueField.addEventListener('blur', function(e) {
            const value = parseFloat(e.target.value);
            if (!isNaN(value)) {
                e.target.value = value.toFixed(2);
            }
        });
    });
}

// Animation on scroll for mobile cards
function initializeScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-fade-in');
            }
        });
    }, observerOptions);

    // Observe mobile cards
    const mobileCards = document.querySelectorAll('.mobile-client-card');
    mobileCards.forEach(card => {
        observer.observe(card);
    });
}

// Haptic feedback simulation
function initializeHapticFeedback() {
    const hapticElements = document.querySelectorAll('.haptic-feedback');
    
    hapticElements.forEach(element => {
        element.addEventListener('touchstart', function() {
            // Visual feedback
            this.style.transform = 'scale(0.98)';
            
            // Vibration API (if supported)
            if ('vibrate' in navigator) {
                navigator.vibrate(10);
            }
        });
        
        element.addEventListener('touchend', function() {
            setTimeout(() => {
                this.style.transform = '';
            }, 100);
        });
    });
}

// Pull to refresh functionality (mobile)
function initializePullToRefresh() {
    let startY = 0;
    let currentY = 0;
    let pulling = false;
    const pullThreshold = 100;
    
    const mobileContainer = document.querySelector('.mobile-client-cards');
    if (!mobileContainer) return;
    
    // Add pull to refresh indicator
    const pullIndicator = document.createElement('div');
    pullIndicator.className = 'pull-to-refresh';
    pullIndicator.innerHTML = '<i class="bi bi-arrow-down-circle"></i> Puxe para atualizar';
    pullIndicator.style.display = 'none';
    mobileContainer.insertBefore(pullIndicator, mobileContainer.firstChild);
    
    mobileContainer.addEventListener('touchstart', function(e) {
        startY = e.touches[0].clientY;
        pulling = window.scrollY === 0;
    });
    
    mobileContainer.addEventListener('touchmove', function(e) {
        if (!pulling) return;
        
        currentY = e.touches[0].clientY;
        const pullDistance = Math.max(0, currentY - startY);
        
        if (pullDistance > 10) {
            e.preventDefault();
            pullIndicator.style.display = 'block';
            pullIndicator.style.transform = `translateY(${Math.min(pullDistance, pullThreshold)}px)`;
            
            if (pullDistance >= pullThreshold) {
                pullIndicator.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Solte para atualizar';
            }
        }
    });
    
    mobileContainer.addEventListener('touchend', function(e) {
        if (!pulling) return;
        
        const pullDistance = currentY - startY;
        
        if (pullDistance >= pullThreshold) {
            // Refresh page
            window.location.reload();
        } else {
            // Reset indicator
            pullIndicator.style.display = 'none';
            pullIndicator.style.transform = '';
            pullIndicator.innerHTML = '<i class="bi bi-arrow-down-circle"></i> Puxe para atualizar';
        }
        
        pulling = false;
    });
}

// Sort table functionality (desktop)
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
        if (columnIndex === 3) { // Value column
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
    if (currentHeader) {
        currentHeader.className = isAscending ? 
            'bi bi-arrow-up ms-1' : 
            'bi bi-arrow-down ms-1';
    }
}

// Export clients data
function exportClients() {
    const table = document.getElementById('clientsTable');
    if (!table) {
        // For mobile, create data from cards
        const cards = document.querySelectorAll('.mobile-client-card:not([style*="display: none"])');
        const data = [];
        
        cards.forEach(card => {
            const name = card.querySelector('.mobile-client-name').textContent;
            const plan = card.querySelector('.mobile-client-plan').textContent;
            const phone = card.dataset.phone;
            const status = card.dataset.status;
            
            data.push({
                'Cliente': name,
                'Plano': plan,
                'Telefone': phone,
                'Status': status
            });
        });
        
        downloadCSV(data, 'clientes-mobile');
        return;
    }

    // Desktop export
    const data = [];
    const headers = Array.from(table.querySelectorAll('thead th'))
        .slice(0, -1) // Remove actions column
        .map(th => th.textContent.trim());

    const rows = table.querySelectorAll('tbody tr:not([style*="display: none"])');
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

    downloadCSV(data, 'clientes-desktop');
}

function downloadCSV(data, filename) {
    if (data.length === 0) return;
    
    const headers = Object.keys(data[0]);
    const csvContent = [
        headers.join(','),
        ...data.map(row => headers.map(header => `"${row[header] || ''}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${filename}-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
}

// Initialize page functionality
document.addEventListener('DOMContentLoaded', function() {
    // Initialize form validation
    validateClientForm();
    formatPhoneInput();
    formatCurrencyInput();
    
    // Initialize filters
    initializeMobileFilters();
    initializeDesktopFilters();
    
    // Initialize animations and interactions
    initializeScrollAnimations();
    initializeHapticFeedback();
    initializePullToRefresh();
    initializeTableSort();
    
    // Add smooth animations for mobile cards
    const mobileCards = document.querySelectorAll('.mobile-client-card');
    mobileCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.3s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
    
    // Add smooth animations for desktop rows
    const desktopRows = document.querySelectorAll('#clientsTable tbody tr');
    desktopRows.forEach((row, index) => {
        row.style.opacity = '0';
        row.style.transform = 'translateX(-20px)';
        
        setTimeout(() => {
            row.style.transition = 'all 0.3s ease';
            row.style.opacity = '1';
            row.style.transform = 'translateX(0)';
        }, index * 50);
    });
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Service Worker for offline functionality (future enhancement)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js')
            .then(function(registration) {
                console.log('ServiceWorker registration successful');
            })
            .catch(function(err) {
                console.log('ServiceWorker registration failed: ', err);
            });
    });
}

// Performance optimization: Lazy loading for images (if any)
function initializeLazyLoading() {
    const images = document.querySelectorAll('img[data-src]');
    
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.remove('lazy');
                imageObserver.unobserve(img);
            }
        });
    });
    
    images.forEach(img => imageObserver.observe(img));
}
