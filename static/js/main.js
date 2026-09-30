/**
 * College Complaint Registration and Resolution Portal
 * Client-Side JavaScript Logic
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Initialize Bootstrap Tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 2. Client-Side Bootstrap Form Validation
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // 3. File Upload Client-side Size & Extension Validation
    const fileInput = document.getElementById('attachment');
    if (fileInput) {
        fileInput.addEventListener('change', function () {
            const file = this.files[0];
            if (file) {
                const maxSize = 5 * 1024 * 1024; // 5 MB
                const allowedExtensions = ['jpg', 'jpeg', 'png', 'pdf'];
                const fileExt = file.name.split('.').pop().toLowerCase();

                if (!allowedExtensions.includes(fileExt)) {
                    alert('Invalid file format! Please upload only JPG, PNG, or PDF documents.');
                    this.value = '';
                    return;
                }

                if (file.size > maxSize) {
                    alert('File size exceeds the 5MB limit. Please upload a smaller file.');
                    this.value = '';
                    return;
                }
            }
        });
    }

    // 4. Auto-dismiss Alert Messages after 6 seconds
    const flashAlerts = document.querySelectorAll('.alert-dismissible');
    flashAlerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 6000);
    });

    // 5. Password Confirmation Validation on Registration Form
    const regPassword = document.getElementById('reg_password');
    const regConfirm = document.getElementById('reg_confirm_password');
    if (regPassword && regConfirm) {
        function validatePasswordMatch() {
            if (regPassword.value !== regConfirm.value) {
                regConfirm.setCustomValidity("Passwords do not match");
            } else {
                regConfirm.setCustomValidity('');
            }
        }
        regPassword.addEventListener('change', validatePasswordMatch);
        regConfirm.addEventListener('keyup', validatePasswordMatch);
    }
});

/**
 * Helper function to copy Complaint Code to clipboard
 */
function copyToClipboard(text) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () {
            showToastMessage('Complaint Code copied to clipboard: ' + text);
        }).catch(function () {
            fallbackCopy(text);
        });
    } else {
        fallbackCopy(text);
    }
}

function fallbackCopy(text) {
    const tempInput = document.createElement('input');
    tempInput.value = text;
    document.body.appendChild(tempInput);
    tempInput.select();
    document.execCommand('copy');
    document.body.removeChild(tempInput);
    showToastMessage('Complaint Code copied to clipboard: ' + text);
}

function showToastMessage(msg) {
    const toastBox = document.createElement('div');
    toastBox.className = 'position-fixed bottom-0 end-0 p-3';
    toastBox.style.zIndex = '9999';
    toastBox.innerHTML = `
        <div class="toast align-items-center text-white bg-dark border-0 show" role="alert">
            <div class="d-flex">
                <div class="toast-body"><i class="bi bi-check-circle-fill text-success me-2"></i> ${msg}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    document.body.appendChild(toastBox);
    setTimeout(() => {
        toastBox.remove();
    }, 3500);
}
