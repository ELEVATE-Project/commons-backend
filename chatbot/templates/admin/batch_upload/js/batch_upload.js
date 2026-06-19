// ============================================
// SECTION 1: INITIALIZATION & CONFIGURATION
// ============================================

// CSRF token for Django
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const existingManualTags = JSON.parse(document.getElementById('existing-manual-tags').textContent);
const masterDocumentTypes = JSON.parse(document.getElementById('master-document-types').textContent);
let selectedOrganization = null;
let userDefaultCompany = null;
let pendingOrgSelection = null;

const csrftoken = getCookie('csrftoken');
let expandedSubdocumentPaths = new Set();
const DEFAULT_BOT_ID = {{ default_bot_id|default:"null" }};

// Dynamic file types from Django
const fileTypesData = JSON.parse(document.getElementById('file-types-data').textContent);
const mediaTypesJS = [
    {% for value, label in media_types %}
    { value: "{{ value }}", label: "{{ label }}" },
    {% endfor %}
];

// Create valid MIME types array and extension regex
const validTypes = fileTypesData.map(ft => ft.mime_type);
const validExtensions = fileTypesData
    .map(ft => ft.extension.replace('.', ''))
    .filter(ext => ext)
    .join('|');
const extensionRegex = new RegExp(`\\.(${validExtensions})$`, 'i');

// Global variables
let uploadedFiles = [];
let extractedData = [];
let currentStep = 1;
let currentPage = 1;
let itemsPerPage = 1;
let totalPages = 1;
let pollingInterval = null;
let isExtracting = false;
let sessionId = null;
let isWaitingForAI = false;
let lastSaveTimer = null;
let expandedSubdocument = null;
let userCompanyName = '';

// Media types and priorities from Django
const mediaTypes = {{ media_types|safe }};
const priorities = {{ priorities|safe }};
const BOT_PROFILE_ID = 1;

{% if user.is_authenticated %}
    {% with user_profile=user.profile %}
        {% if user_profile and user_profile.company %}
            userCompanyName = "{{ user_profile.company.name|escapejs }}";
        {% endif %}
    {% endwith %}
{% endif %}

{% if user_company %}
userDefaultCompany = {
    slug: "{{ user_company.slug|escapejs }}",
    name: "{{ user_company.name|escapejs }}"
};
{% endif %}

// File status constants
const FILE_STATUS = {
    PENDING: 'pending',
    PROCESSING: 'processing',
    SUCCESS: 'success',
    ERROR: 'error',
    SKIPPED: 'skipped'
};

// ============================================
// SECTION 3: STEP 1 - UPLOAD FUNCTIONS
// ============================================
// Organization selection
function initializeOrganizationSelect() {
    const orgSelect = document.getElementById('organizationSelect');

    // Set default selection
    if (userDefaultCompany) {
        orgSelect.value = userDefaultCompany.slug;
        selectedOrganization = userDefaultCompany;
    }

    // Add change event listener
    orgSelect.addEventListener('change', function() {
        const selectedSlug = this.value;
        const selectedName = this.options[this.selectedIndex].getAttribute('data-name');

        if (!selectedSlug) {
            selectedOrganization = null;
            return;
        }

        const newSelection = {
            slug: selectedSlug,
            name: selectedName
        };

        // Check if different from user's default company
        if (userDefaultCompany && selectedSlug !== userDefaultCompany.slug) {
            // Show confirmation modal
            pendingOrgSelection = newSelection;
            document.getElementById('selectedOrgName').textContent = selectedName;
            document.getElementById('orgConfirmModal').style.display = 'block';
        } else {
            selectedOrganization = newSelection;
        }
    });
}

function confirmOrgSelection(confirmed) {
    const modal = document.getElementById('orgConfirmModal');
    const orgSelect = document.getElementById('organizationSelect');

    if (confirmed && pendingOrgSelection) {
        selectedOrganization = pendingOrgSelection;
    } else {
        // Revert to default
        if (userDefaultCompany) {
            orgSelect.value = userDefaultCompany.slug;
            selectedOrganization = userDefaultCompany;
        } else {
            orgSelect.value = '';
            selectedOrganization = null;
        }
    }

    modal.style.display = 'none';
    pendingOrgSelection = null;
}

function validateOrganizationSelection() {
    if (!selectedOrganization) {
        showStatus('Please select an organization before uploading files', 'error');
        return false;
    }
    return true;
}

// Initialize with default bot selected
window.addEventListener('DOMContentLoaded', function() {
    initializeOrganizationSelect();
    resetToDefaultBot();
});

function resetToDefaultBot() {
    const selectElement = document.getElementById('companyBotSelect');
    if (selectElement) {
        if (DEFAULT_BOT_ID) {
            selectElement.value = DEFAULT_BOT_ID;
        } else {
            // If no default, select the first bot
            const firstOption = selectElement.querySelector('option[value]:not([value=""])');
            if (firstOption) {
                selectElement.value = firstOption.value;
            }
        }
    }
}


// ============================================
// SECTION 2: SHARED UTILITIES
// ============================================
// Status & Loading functions

function showStatus(message, type = 'info') {
    const statusEl = document.getElementById('statusMessage');
    statusEl.textContent = message;
    statusEl.className = `status-message ${type}`;
    statusEl.style.display = 'block';

    if (type !== 'error') {
        setTimeout(() => {
            statusEl.style.display = 'none';
        }, 5000);
    }
}

function showLoading(text = 'Processing...') {
    const loadingTextEl = document.getElementById('loadingText');
    if (text.includes('<br>') || text.includes('<small>')) {
        loadingTextEl.innerHTML = text;
    } else {
        loadingTextEl.textContent = text;
    }
    document.getElementById('loadingOverlay').style.display = 'flex';

}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

function updateStepIndicator(step) {
    document.querySelectorAll('.step').forEach((el, index) => {
        if (index + 1 < step) {
            el.classList.add('completed');
            el.classList.remove('active');
        } else if (index + 1 === step) {
            el.classList.add('active');
            el.classList.remove('completed');
        } else {
            el.classList.remove('active', 'completed');
        }
    });

    document.querySelectorAll('.content-section').forEach(el => {
        el.classList.remove('active');
    });
    document.getElementById(`step${step}`).classList.add('active');

    currentStep = step;
}

// ============================================
// SECTION 6: EVENT HANDLERS
// ============================================
// Upload area events
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');

uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
});

async function handleFiles(files) {
    // Check if bot is selected
    if (!validateOrganizationSelection()) {
        return;
    }

    const companyBotId = document.getElementById('companyBotSelect').value;
    if (!companyBotId) {
        showStatus('Please select a company bot before uploading files', 'error');
        return;
    }
    // Generate session ID if not exists
    if (!sessionId) {
        sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    const filesToUpload = [];
    const unsupportedFiles = [];

    Array.from(files).forEach(file => {
        // Check both MIME type and file extension
        if (validTypes.includes(file.type) || (file.name && file.name.match(extensionRegex))) {
            if (!uploadedFiles.find(f => f.name === file.name)) {
                const fileData = {
                    file: file,
                    name: file.name,
                    size: file.size,
                    status: FILE_STATUS.PENDING,
                    error: null,
                    errorTimestamp: null,
                    index: uploadedFiles.length
                };
                uploadedFiles.push(fileData);
                filesToUpload.push(fileData);
            }
        } else {
            unsupportedFiles.push(file.name);
        }
    });

    // Show errors for unsupported files
    if (unsupportedFiles.length > 0) {
        const supportedTypes = fileTypesData.map(ft => ft.label).join(', ');
        const unsupportedList = unsupportedFiles.join(', ');
        showStatus(
            `Unsupported file format${unsupportedFiles.length > 1 ? 's' : ''}: ${unsupportedList}. ` +
            `Supported formats: ${supportedTypes}`,
            'error'
        );
    }

    // Hide the upload area after files are selected
    const uploadArea = document.getElementById('uploadArea');
    if (uploadArea) {
        uploadArea.style.display = 'none';
    }

    // Show a message about adding more files
    const uploadSection = document.querySelector('#step1 .upload-area').parentElement;
    if (!document.getElementById('addMoreFilesMessage')) {
        const addMoreMessage = document.createElement('div');
        addMoreMessage.id = 'addMoreFilesMessage';
        addMoreMessage.className = 'info-message';
        addMoreMessage.innerHTML = `
            <div style="text-align: center; color: #666; margin: 20px 0;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#417690" stroke-width="2" style="vertical-align: middle; margin-right: 8px;">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="16" x2="12" y2="12"></line>
                    <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
                <strong>Files added successfully!</strong>
            </div>
            <div style="text-align: center; margin: 15px 0;">
                <p style="color: #1976d2; font-size: 14px; margin: 5px 0;">
                    To add more files, please refresh the page.
                </p>
                <p style="color: #d32f2f; font-size: 13px; margin: 5px 0;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#d32f2f" stroke-width="2" style="vertical-align: middle; margin-right: 5px;">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                        <line x1="12" y1="9" x2="12" y2="13"></line>
                        <line x1="12" y1="17" x2="12.01" y2="17"></line>
                    </svg>
                    <strong>Warning:</strong> Refreshing the page will lose all currently uploaded files that haven't been saved to the database yet.
                </p>
            </div>
            <div style="text-align: center; margin-top: 15px;">
                <button onclick="location.reload()" class="btn btn-secondary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-right: 5px;">
                        <path d="M23 4v6h-6"></path>
                        <path d="M1 20v-6h6"></path>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                    Refresh Page to Add More Files
                </button>
            </div>
        `;
        uploadSection.appendChild(addMoreMessage);
    }

    // Update the file list display first to show pending files
    updateFileList();

    // If there are files to upload, process them immediately
    if (filesToUpload.length > 0) {
        showLoading(`Uploading ${filesToUpload.length} file(s)...`);
        await processFiles(filesToUpload);
    } else if (unsupportedFiles.length > 0 && filesToUpload.length === 0) {
        // If all files were unsupported, show the upload area again
        if (uploadedFiles.length === 0) {
            uploadArea.style.display = 'block';
            const addMoreMessage = document.getElementById('addMoreFilesMessage');
            if (addMoreMessage) {
                addMoreMessage.remove();
            }
        }
    }

    fileInput.value = '';
}

// New function to process files immediately after selection
async function processFiles(files) {
    isExtracting = true;
    updateExtractionProgress();
    document.getElementById('extractionProgress').classList.add('show');

    const results = await extractDataFromFiles(files);

    // Add results to extractedData
    results.forEach(result => {
        const existingIndex = extractedData.findIndex(item => item.file_index === result.file_index);
        if (existingIndex >= 0) {
            extractedData[existingIndex] = result;
        } else {
            extractedData.push(result);
        }
    });

    // Check if there are any AI extraction tasks to wait for
    const tasksToWaitFor = extractedData
        .filter(item => item.status === FILE_STATUS.SUCCESS && item.data && item.data.auto_tag_task_id && !item.data.auto_tags_ready)
        .map(item => item.data.auto_tag_task_id);

    if (tasksToWaitFor.length > 0) {
        isWaitingForAI = true;
        document.getElementById('aiStatus').style.display = 'inline';

        try {
            await waitForAllTasksToComplete(tasksToWaitFor);
        } catch (error) {
            console.error('AI enhancement error:', error);
        } finally {
            isWaitingForAI = false;
            document.getElementById('aiStatus').style.display = 'none';
        }
    }

    isExtracting = false;
    updateFileList();
    updateFailedLinks();
    updateButtonStates();

    // Ensure loading overlay is hidden (this may be redundant now but good as safety)
    hideLoading();
}

function isDocumentTypeField(key) {
    return key && key.toUpperCase() === 'DOCUMENT TYPE';
}

function createDocumentTypeDropdown(path, kvIndex, currentValue = '') {
    const dropdownId = `docTypeDropdown_${path}_${kvIndex}`;
    const listId = `docTypeDropdownList_${path}_${kvIndex}`;

    return `
        <div class="custom-dropdown" id="customDocTypeDropdown_${path}_${kvIndex}">
            <input type="text"
                   class="dropdown-search"
                   placeholder="Search or enter document type..."
                   value="${currentValue}"
                   onclick="toggleDocumentTypeDropdown('${path}', ${kvIndex})"
                   oninput="filterDocumentTypeDropdown('${path}', ${kvIndex}, this.value)"
                   onkeypress="handleDocumentTypeDropdownKeypress(event, '${path}', ${kvIndex})"
                   onchange="saveKeyValueByPath('${path}', ${kvIndex}, 'value', this.value); autoResizeTextarea(this)"
>
            <div class="dropdown-list" id="${listId}">
                ${masterDocumentTypes.map(docType => `
                    <div class="dropdown-option" onclick="selectDocumentTypeFromDropdown('${path}', ${kvIndex}, '${docType.replace(/'/g, "\\'")}')">
                        ${docType}
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

// Function to toggle document type dropdown
function toggleDocumentTypeDropdown(path, kvIndex) {
    const listId = `docTypeDropdownList_${path}_${kvIndex}`;
    const dropdown = document.getElementById(listId);
    if (!dropdown) return;

    const isVisible = dropdown.classList.contains('show');

    // Close all other dropdowns
    document.querySelectorAll('.dropdown-list').forEach(dl => {
        dl.classList.remove('show');
    });

    // Toggle current dropdown
    if (!isVisible) {
        dropdown.classList.add('show');
        filterDocumentTypeDropdown(path, kvIndex, '');
    }
}

// Function to filter document type dropdown
function filterDocumentTypeDropdown(path, kvIndex, searchTerm) {
    const listId = `docTypeDropdownList_${path}_${kvIndex}`;
    const dropdown = document.getElementById(listId);
    if (!dropdown) return;

    const filteredTypes = masterDocumentTypes.filter(docType =>
        docType.toLowerCase().includes(searchTerm.toLowerCase())
    );

    if (filteredTypes.length > 0) {
        dropdown.innerHTML = filteredTypes.map(docType => {
            const escapedType = docType.replace(/'/g, "\\'");
            return `
                <div class="dropdown-option" onclick="selectDocumentTypeFromDropdown('${path}', ${kvIndex}, '${escapedType}')">
                    ${docType}
                </div>
            `;
        }).join('');
    } else if (searchTerm.trim()) {
        dropdown.innerHTML = `
            <div class="dropdown-option no-results">
                No matching document types found
            </div>
        `;
    } else {
        dropdown.innerHTML = masterDocumentTypes.map(docType => {
            const escapedType = docType.replace(/'/g, "\\'");
            return `
                <div class="dropdown-option" onclick="selectDocumentTypeFromDropdown('${path}', ${kvIndex}, '${escapedType}')">
                    ${docType}
                </div>
            `;
        }).join('');
    }

    dropdown.classList.add('show');
}

// Function to select document type from dropdown
function selectDocumentTypeFromDropdown(path, kvIndex, docType) {
    const listId = `docTypeDropdownList_${path}_${kvIndex}`;
    const dropdown = document.getElementById(listId);
    const searchInput = dropdown.previousElementSibling;

    dropdown.classList.remove('show');
    searchInput.value = docType;

    // Save the value based on whether this is a path (subdocument) or index (main document)
    if (path.includes('_')) {
        // This is a subdocument path
        saveKeyValueByPath(path, kvIndex, 'value', docType);
    } else {
        // This is a main document index
        saveKeyValueData(parseInt(path), kvIndex, 'value', docType);
    }
}

// Function to handle document type dropdown keypress
function handleDocumentTypeDropdownKeypress(event, path, kvIndex) {
    if (event.key === 'Enter') {
        event.preventDefault();
        const searchTerm = event.target.value.trim();
        const listId = `docTypeDropdownList_${path}_${kvIndex}`;
        const dropdown = document.getElementById(listId);

        if (searchTerm) {
            // Check if exact match exists
            const exactMatch = masterDocumentTypes.find(docType =>
                docType.toLowerCase() === searchTerm.toLowerCase()
            );

            if (exactMatch) {
                selectDocumentTypeFromDropdown(path, kvIndex, exactMatch);
            } else {
                // Use the typed value as is (allows manual entry)
                dropdown.classList.remove('show');

                // Save based on whether this is a path (subdocument) or index (main document)
                if (path.includes('_')) {
                    saveKeyValueByPath(path, kvIndex, 'value', searchTerm);
                } else {
                    saveKeyValueData(parseInt(path), kvIndex, 'value', searchTerm);
                }
            }
        }
    } else if (event.key === 'Escape') {
        const listId = `docTypeDropdownList_${path}_${kvIndex}`;
        const dropdown = document.getElementById(listId);
        dropdown.classList.remove('show');
        event.target.blur();
    }
}

// Updated function for rendering key-values in subdocuments with document type dropdown
function updateKeyValueHtmlWithDocTypeDropdown(subdoc, path) {
    return subdoc.key_values.map((kv, kvIndex) => {
        const isDocType = isDocumentTypeField(kv.key);
        const isOrganization = kv.key === 'ORGANIZATION';
        const isAiExtracted = kv.source === 'ai' || isOrganization || isDocType;
        const isUserAdded = kv.source === 'user';

        // Ensure kv.value is a string before processing
        const kvValue = kv.value || '';
        const safeKvValue = typeof kvValue === 'string' ? kvValue : String(kvValue);

        // Enhanced textarea classes that consider structured content
        const targetItem = { data: subdoc };
        const textareaClasses = getTextareaClasses(safeKvValue, kv.key, targetItem);

        // Key input styling and properties
        const keyInputProps = isAiExtracted ?
            'readonly style="background-color: #f8f9fa; cursor: not-allowed;"' :
            'class="editable-field" onchange="saveKeyValueByPath(\'' + path + '\', ' + kvIndex + ', \'key\', this.value)"';

        // Remove button visibility
        const removeButtonStyle = isUserAdded ? '' : 'style="display: none;"';

        if (isDocType) {
            return `
                <div class="key-value-pair structured-content-kv">
                    <input type="text"
                       class="kv-key-input ${isUserAdded ? 'editable-field' : ''}"
                       value="${kv.key || ''}"
                       id="key_${path}_${kvIndex}"
                       placeholder="Key"
                       ${keyInputProps}>
                    <div class="kv-value-container">
                        ${createDocumentTypeDropdown(path, kvIndex, safeKvValue)}
                    </div>
                    <button class="remove-kv-btn" onclick="removeKeyValueByPath('${path}', ${kvIndex})" ${removeButtonStyle}>Remove</button>
                </div>
            `;
        } else if (isOrganization) {
            return `
                <div class="key-value-pair structured-content-kv">
                    <input type="text"
                           class="kv-key-input"
                           value="${kv.key || ''}"
                           id="key_${path}_${kvIndex}"
                           placeholder="Key"
                           readonly
                           style="background-color: #f8f9fa; cursor: not-allowed;">
                    <textarea class="${textareaClasses}"
                              id="value_${path}_${kvIndex}"
                              readonly
                              style="background-color: #f8f9fa; cursor: not-allowed; resize: none;"
                              title="Organization is inherited from parent document selection">${safeKvValue}</textarea>
                    <button class="remove-kv-btn" onclick="removeKeyValueByPath('${path}', ${kvIndex})" style="display: none;">Remove</button>
                </div>
            `;
        } else {
            // Add placeholder text for array fields
            const isArrayField = shouldPreserveAsArray(safeKvValue, kv.key, targetItem);
            const placeholder = isArrayField ?
                "Enter list items (one per line, use • for bullet points)" :
                "Value";

            return `
                <div class="key-value-pair structured-content-kv">
                    <input type="text"
                       class="kv-key-input ${isUserAdded ? 'editable-field' : ''}"
                       value="${kv.key || ''}"
                       id="key_${path}_${kvIndex}"
                       placeholder="Key"
                       ${keyInputProps}>
                    <textarea class="${textareaClasses} editable-field"
                          id="value_${path}_${kvIndex}"
                          placeholder="${placeholder}"
                          onchange="saveKeyValueByPath('${path}', ${kvIndex}, 'value', this.value); autoResizeTextarea(this)"
                          oninput="autoResizeTextarea(this)">${safeKvValue}
                    </textarea>
                    <button class="remove-kv-btn" onclick="removeKeyValueByPath('${path}', ${kvIndex})" ${removeButtonStyle}>Remove</button>
                </div>
            `;
        }
    }).join('');
}

function isFormattedListContent(content) {
    // Ensure content is a string before calling string methods
    if (!content || typeof content !== 'string') {
        return false;
    }

    return content.includes('•') ||
           content.includes('\n') ||
           content.length > 200;
}

function getTextareaClasses(content, key = null, item = null) {
    let classes = 'key-value-textarea';

    // Check if this should be treated as an array field
    if (key && item && shouldPreserveAsArray(content, key, item)) {
        classes += ' formatted-list';
        if (content && content.length > 200) {
            classes += ' long-content';
        }
    } else if (isFormattedListContent(content)) {
        classes += ' formatted-list';
        if (content && content.length > 200) {
            classes += ' long-content';
        }
    }

    return classes;
}


// Updated function for rendering key-values in main documents with structured content support
function updateMainDocumentKeyValueHtml(item, displayIndex) {
    return (item.data.key_values || []).map((kv, kvIndex) => {
        const isDocType = isDocumentTypeField(kv.key);
        const isOrganization = kv.key === 'ORGANIZATION';
        const isAiExtracted = kv.source === 'ai' || isOrganization || isDocType; // AI-extracted or special fields
        const isUserAdded = kv.source === 'user';

        // Ensure kv.value is a string before processing
        const kvValue = kv.value || '';
        const safeKvValue = typeof kvValue === 'string' ? kvValue : String(kvValue);

        // Enhanced textarea classes that consider structured content
        const textareaClasses = getTextareaClasses(safeKvValue, kv.key, item);

        // Key input styling and properties
        // Key input styling and properties
        const keyInputProps = isAiExtracted ?
            'readonly style="background-color: #f8f9fa; cursor: not-allowed;"' :
            'class="editable-field" onchange="saveKeyValueData(' + displayIndex + ', ' + kvIndex + ', \'key\', this.value)"';

        // Remove button visibility
        const removeButtonStyle = isUserAdded ? '' : 'style="display: none;"';

        if (isDocType) {
            return `
                <div class="key-value-pair structured-content-kv">
                    <input type="text"
                        class="kv-key-input ${isUserAdded ? 'editable-field' : ''}"
                       value="${kv.key || ''}"
                       id="key_${displayIndex}_${kvIndex}"
                       placeholder="Key"
                       ${keyInputProps}>
                    <div class="kv-value-container">
                        ${createDocumentTypeDropdown(displayIndex, kvIndex, safeKvValue)}
                    </div>
                    <button class="remove-kv-btn" onclick="removeKeyValue(${displayIndex}, ${kvIndex})" ${removeButtonStyle}>Remove</button>
                </div>
            `;
        } else if (isOrganization) {
            return `
                <div class="key-value-pair structured-content-kv">
                    <input type="text"
                           class="kv-key-input"
                           value="${kv.key || ''}"
                           id="key_${displayIndex}_${kvIndex}"
                           placeholder="Key"
                           readonly
                           style="background-color: #f8f9fa; cursor: not-allowed;">
                    <textarea class="${textareaClasses}"
                              id="value_${displayIndex}_${kvIndex}"
                              readonly
                              style="background-color: #f8f9fa; cursor: not-allowed; resize: none;"
                              title="Organization is set from the dropdown selection above">${safeKvValue}</textarea>
                    <button class="remove-kv-btn" onclick="removeKeyValue(${displayIndex}, ${kvIndex})" style="display: none;">Remove</button>
                </div>
            `;
        } else {
            // Add placeholder text for array fields
            const isArrayField = shouldPreserveAsArray(safeKvValue, kv.key, item);
            const placeholder = isArrayField ?
                "Enter list items (one per line, use • for bullet points)" :
                "Value";

            return `
                <div class="key-value-pair structured-content-kv">
                    <input type="text"
                        class="kv-key-input ${isUserAdded ? 'editable-field' : ''}"
                       value="${kv.key || ''}"
                       id="key_${displayIndex}_${kvIndex}"
                       placeholder="Key"
                       ${keyInputProps}>
                    <textarea class="${textareaClasses} editable-field"
                      id="value_${displayIndex}_${kvIndex}"
                      placeholder="${placeholder}"
                      onchange="saveKeyValueData(${displayIndex}, ${kvIndex}, 'value', this.value)"
                      oninput="autoResizeTextarea(this)">${safeKvValue}
                    </textarea>
                    <button class="remove-kv-btn" onclick="removeKeyValue(${displayIndex}, ${kvIndex})" ${removeButtonStyle}>Remove</button>
                </div>
            `;
        }
    }).join('');
}

// Modified function to show files in separate sections
function updateFileList() {
    const successfulFiles = uploadedFiles.filter(f => f.status === FILE_STATUS.SUCCESS || f.status === FILE_STATUS.PENDING || f.status === FILE_STATUS.PROCESSING);
    const failedFiles = uploadedFiles.filter(f => f.status === FILE_STATUS.ERROR);
    const skippedFiles = uploadedFiles.filter(f => f.status === FILE_STATUS.SKIPPED);

    // Get references to UI elements
    const uploadArea = document.getElementById('uploadArea');
    const addMoreMessage = document.getElementById('addMoreFilesMessage');
    const successfulSection = document.getElementById('successfulSection');
    const successfulList = document.getElementById('successfulFilesList');
    const successfulCount = document.getElementById('successfulCount');
    const failedSection = document.getElementById('failedSection');
    const failedList = document.getElementById('failedFilesList');
    const failedCount = document.getElementById('failedCount');

    // Check if we have any files at all
    const hasAnyFiles = uploadedFiles.length > 0;

    // Show/hide upload area based on whether we have files
    if (!hasAnyFiles) {
        // No files at all - show upload area, hide message
        if (uploadArea) {
            uploadArea.style.display = 'block';
        }
        if (addMoreMessage) {
            addMoreMessage.remove();
        }
    } else {
        // Have files - hide upload area, show message
        if (uploadArea) {
            uploadArea.style.display = 'none';
        }

        // Add "add more files" message if not already present
        if (!addMoreMessage) {
            const uploadSection = document.querySelector('#step1 .upload-area').parentElement;
            const newMessage = document.createElement('div');
            newMessage.id = 'addMoreFilesMessage';
            newMessage.className = 'info-message';
            newMessage.innerHTML = `
                <div style="text-align: center; color: #666; margin: 20px 0;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#417690" stroke-width="2" style="vertical-align: middle; margin-right: 8px;">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    <strong>Files added successfully!</strong>
                </div>
                <div style="text-align: center; margin: 15px 0;">
                    <p style="color: #1976d2; font-size: 14px; margin: 5px 0;">
                        To add more files, please refresh the page.
                    </p>
                    <p style="color: #d32f2f; font-size: 13px; margin: 5px 0;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#d32f2f" stroke-width="2" style="vertical-align: middle; margin-right: 5px;">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                            <line x1="12" y1="9" x2="12" y2="13"></line>
                            <line x1="12" y1="17" x2="12.01" y2="17"></line>
                        </svg>
                        <strong>Warning:</strong> Refreshing the page will lose all currently uploaded files that haven't been saved to the database yet.
                    </p>
                </div>
                <div style="text-align: center; margin-top: 15px;">
                    <button onclick="location.reload()" class="btn btn-secondary">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-right: 5px;">
                            <path d="M23 4v6h-6"></path>
                            <path d="M1 20v-6h6"></path>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                        Refresh Page to Add More Files
                    </button>
                </div>
            `;
            uploadSection.appendChild(newMessage);
        }
    }

    // Update successful files section
    if (successfulFiles.length > 0 || skippedFiles.length > 0) {
        if (successfulSection) {
            successfulSection.style.display = 'block';
        }
        if (successfulCount) {
            successfulCount.textContent = `(${successfulFiles.length})`;
        }

        if (successfulList) {
            successfulList.innerHTML = '';
            [...successfulFiles, ...skippedFiles].forEach(fileData => {
                const fileItem = createFileItem(fileData);
                successfulList.appendChild(fileItem);
            });
        }
    } else {
        if (successfulSection) {
            successfulSection.style.display = 'none';
        }
    }

    // Update failed files section
    if (failedFiles.length > 0) {
        if (failedSection) {
            failedSection.style.display = 'block';
        }
        if (failedCount) {
            failedCount.textContent = `(${failedFiles.length})`;
        }

        const sectionHeader = failedSection ? failedSection.querySelector('.section-header') : null;
        if (sectionHeader) {
            sectionHeader.innerHTML = `
                <div>
                    <span class="section-title">Failed Uploads</span>
                    <span class="section-count" id="failedCount">(${failedFiles.length})</span>
                </div>
            `;
        }

        if (failedList) {
            failedList.innerHTML = '';
            failedFiles.forEach(fileData => {
                const fileItem = createFileItem(fileData);
                failedList.appendChild(fileItem);
            });
        }
    } else {
        if (failedSection) {
            failedSection.style.display = 'none';
        }
    }

    updateButtonStates();
    updateExtractionProgress();
    updateFailedLinks(); // Always update failed links when file list updates
}

function updateFailedLinks() {
    // Find all files with failed links
    let allFailedLinks = [];

    extractedData.forEach((item, fileIndex) => {
        if (item.status === FILE_STATUS.SUCCESS && item.data && item.data.failed_links) {
            item.data.failed_links.forEach((failedLink, linkIndex) => {
                // Extract the URL from the failed link structure
                let url = '';
                if (failedLink.file_url) {
                    url = failedLink.file_url;
                } else if (failedLink.url && Array.isArray(failedLink.url) && failedLink.url.length > 0) {
                    url = failedLink.url[0];
                } else if (typeof failedLink.url === 'string') {
                    url = failedLink.url;
                }

                // Extract error message
                let errorMessage = '';
                if (failedLink.error) {
                    if (typeof failedLink.error === 'object' && failedLink.error.error) {
                        errorMessage = failedLink.error.error;
                    } else if (typeof failedLink.error === 'string') {
                        errorMessage = failedLink.error;
                    }
                }

                allFailedLinks.push({
                    ...failedLink,
                    url: url,
                    errorMessage: errorMessage,
                    parentFileIndex: fileIndex,
                    parentFileName: item.filename,
                    uniqueIndex: `${fileIndex}_${linkIndex}` // Create unique identifier
                });
            });
        }
    });

    const fileSections = document.getElementById('fileSections');

    // Remove existing failed links section
    const existingSection = document.getElementById('failedLinksSection');
    if (existingSection) {
        existingSection.remove();
    }

    if (allFailedLinks.length > 0) {
        const failedLinksSection = document.createElement('div');
        failedLinksSection.id = 'failedLinksSection';
        failedLinksSection.className = 'failed-links-section';

        failedLinksSection.innerHTML = `
            <div class="failed-links-header">
                <div class="failed-links-title">
                    Failed Link Extractions (${allFailedLinks.length})
                </div>
            </div>
            <div class="failed-links-list">
                ${allFailedLinks.map((failed, index) => `
                    <div class="failed-link-item" id="failed-link-${failed.uniqueIndex}">
                        <div class="failed-link-info">
                            <div class="failed-link-url">${failed.url || 'Unknown URL'}</div>
                            <div class="failed-link-error">${failed.errorMessage || 'Unknown error'}</div>
                            <div style="font-size: 11px; color: #666; margin-top: 2px;">
                                From: ${failed.parentFileName}
                            </div>
                        </div>
                        <div class="failed-link-actions">
                            <button class="skip-btn" onclick="removeFailedLink(${failed.parentFileIndex}, '${encodeURIComponent(failed.url)}', '${failed.uniqueIndex}')">Remove</button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        fileSections.appendChild(failedLinksSection);
    }
}

// Add retry function for failed links
async function retryFailedLink(parentFileIndex, url) {
    showStatus(`Retrying extraction for ${url}...`, 'info');

    // Here you would implement the retry logic
    // This is a placeholder - you'd need to call your backend to retry
    showStatus('Retry functionality not yet implemented', 'warning');
}


function removeFailedLink(parentFileIndex, encodedUrl, failedIndex) {
    const url = decodeURIComponent(encodedUrl);
    const item = extractedData[parentFileIndex];

    if (item && item.data && item.data.failed_links) {
        // Find and remove the failed link by URL
        const originalLength = item.data.failed_links.length;
        item.data.failed_links = item.data.failed_links.filter(link => {
            let linkUrl = '';
            if (link.file_url) {
                linkUrl = link.file_url;
            } else if (link.url && Array.isArray(link.url) && link.url.length > 0) {
                linkUrl = link.url[0];
            } else if (typeof link.url === 'string') {
                linkUrl = link.url;
            }
            return linkUrl !== url;
        });

        // Check if the link was actually removed
        if (item.data.failed_links.length < originalLength) {
            // Mark item as having unsaved changes
            item.hasUnsavedChanges = true;

            // Update the failed links display
            updateFailedLinks();

            // Also update the file list to reflect changes
            updateFileList();

            showStatus(`Removed failed link: ${url}`, 'success');
        } else {
            showStatus(`Failed to remove link: ${url}`, 'error');
        }
    } else {
        showStatus('Failed to find the link to remove', 'error');
    }
}

// New function to create individual file items
function createFileItem(fileData) {
    const fileItem = document.createElement('div');
    fileItem.className = `file-item ${fileData.status}`;
    fileItem.id = `file-item-${fileData.index}`;

    let statusIcon = '';
    let statusText = '';
    let statusActions = '';

    switch (fileData.status) {
        case FILE_STATUS.SUCCESS:
            statusIcon = '✓';
            statusText = 'Upload successful';
            break;
        case FILE_STATUS.ERROR:
            statusIcon = '✗';
            statusText = 'Upload failed';
            statusActions = `
                <button class="error-toggle" onclick="toggleErrorDetails(${fileData.index})">Details</button>
            `;
            break;
        case FILE_STATUS.SKIPPED:
            statusIcon = '⊘';
            statusText = 'Skipped';
            break;
        case FILE_STATUS.PROCESSING:
            statusIcon = '<span class="spinner" style="width: 16px; height: 16px; border-width: 2px;"></span>';
            statusText = 'Uploading...';
            break;
        default:
            statusIcon = '⏳';
            statusText = 'Waiting...';
    }

    fileItem.innerHTML = `
        <div class="file-item-main">
            <div class="file-item-content">
                <div class="file-status-icon">${statusIcon}</div>
                <div class="file-info">
                    <div class="file-name">${fileData.name}</div>
                    <div class="file-size">${(fileData.size / 1024).toFixed(2)} KB</div>
                    <div class="file-status-text">${statusText}</div>
                </div>
            </div>
            <div class="file-actions">
                ${statusActions}
                <button class="remove-btn" onclick="removeFile(${fileData.index})">Remove</button>
            </div>
        </div>
        ${fileData.status === FILE_STATUS.ERROR ? `
            <div class="file-error-details" id="error-details-${fileData.index}">
                <div class="error-details-content">
                    <div class="error-title">Upload Error</div>
                    <div class="error-message">${fileData.error || 'Unknown error occurred'}</div>
                    <div class="error-timestamp">Failed at: ${fileData.errorTimestamp ? new Date(fileData.errorTimestamp).toLocaleString() : 'Unknown time'}</div>
                </div>
            </div>
        ` : ''}
    `;

    return fileItem;
}

function toggleErrorDetails(index) {
    const errorDetails = document.getElementById(`error-details-${index}`);
    if (errorDetails) {
        errorDetails.classList.toggle('show');
    }
}

function updateButtonStates() {
    const hasReadyFiles = uploadedFiles.some(f => f.status === FILE_STATUS.SUCCESS);
    const isProcessing = uploadedFiles.some(f => f.status === FILE_STATUS.PROCESSING);
    const hasFiles = uploadedFiles.length > 0;

    document.getElementById('proceedBtn').disabled = !hasReadyFiles || isProcessing || isWaitingForAI;

    // Show/hide proceed button based on upload state
    const proceedBtn = document.getElementById('proceedBtn');

    if (hasReadyFiles && !isProcessing && !isWaitingForAI) {
        proceedBtn.style.display = 'inline-block';
    } else {
        proceedBtn.style.display = 'none';
    }
}

function updateExtractionProgress() {
    const stats = uploadedFiles.reduce((acc, file) => {
        acc.total++;
        switch (file.status) {
            case FILE_STATUS.SUCCESS:
                acc.success++;
                break;
            case FILE_STATUS.ERROR:
                acc.error++;
                break;
            case FILE_STATUS.PROCESSING:
                acc.processing++;
                break;
            case FILE_STATUS.SKIPPED:
                acc.skipped++;
                break;
        }
        return acc;
    }, { total: 0, success: 0, error: 0, processing: 0, skipped: 0 });

    // Update progress stats
    document.getElementById('successCount').textContent = stats.success;
    document.getElementById('errorCount').textContent = stats.error;

    // Update progress bar
    const completed = stats.success + stats.error + stats.skipped;
    const progress = stats.total > 0 ? (completed / stats.total) * 100 : 0;
    document.getElementById('extractionProgressBar').style.width = progress + '%';

    // Update progress text
    const progressText = document.getElementById('progressText');
    if (stats.processing > 0) {
        progressText.textContent = `Processing ${stats.processing} file(s)...`;
    } else if (completed === stats.total && stats.total > 0) {
        progressText.textContent = `Upload complete! ${stats.success} successful, ${stats.error} failed, ${stats.skipped} skipped.`;
    } else if (stats.total > 0) {
        progressText.textContent = `${completed}/${stats.total} files processed`;
    } else {
        progressText.textContent = 'No files to process';
    }

    // Show/hide progress section
    const progressSection = document.getElementById('extractionProgress');
    if (uploadedFiles.length > 0 && (completed > 0 || stats.processing > 0)) {
        progressSection.classList.add('show');
    } else {
        progressSection.classList.remove('show');
    }
}

function removeFile(index) {
    if (!confirm('Are you sure you want to remove this file from the upload list?')) {
        return;
    }
    // Remove from uploadedFiles
    uploadedFiles = uploadedFiles.filter(f => f.index !== index);

    // Also remove from extractedData
    extractedData = extractedData.filter(item => item.file_index !== index);

    // Reindex remaining files
    uploadedFiles.forEach((file, newIndex) => {
        file.index = newIndex;
        // Update corresponding extracted data index
        const extractedItem = extractedData.find(item => item.filename === file.name);
        if (extractedItem) {
            extractedItem.file_index = newIndex;
        }
    });

    // Update the file list - this will handle showing upload area if no files remain
    updateFileList();

    // If no files remain, also ensure we're back to step 1
    if (uploadedFiles.length === 0) {
        updateStepIndicator(1);
        // Clear session data
        sessionId = null;
        extractedData = [];

        // Hide progress section
        const progressSection = document.getElementById('extractionProgress');
        if (progressSection) {
            progressSection.classList.remove('show');
        }

        showStatus('All files removed. You can now upload new files.', 'info');
    }
}

function skipFile(index) {
    uploadedFiles[index].status = FILE_STATUS.SKIPPED;
    uploadedFiles[index].error = null;
    uploadedFiles[index].errorTimestamp = null;
    updateFileList();
}

function unSkipFile(index) {
    uploadedFiles[index].status = FILE_STATUS.ERROR;
    uploadedFiles[index].error = 'Previously skipped - click Upload Again to retry';
    uploadedFiles[index].errorTimestamp = null;
    updateFileList();
}

// Retry all failed uploads
async function retryAllFailedUploads() {
    const failedFiles = uploadedFiles.filter(f => f.status === FILE_STATUS.ERROR);

    if (failedFiles.length === 0) {
        showStatus('No failed uploads to retry', 'info');
        return;
    }

    showLoading(`Uploading ${failedFiles.length} failed files...`);

    // Process all failed files
    await processFiles(failedFiles);

    // hideLoading is now called inside processFiles
}

// Retry all failed saves
async function retryAllFailed() {
    // Collect all failed items including subdocuments
    const failedItems = [];

    // Add main document failures
    saveResults.forEach((result, index) => {
        if (!result.success) {
            failedItems.push({
                type: 'main',
                index: index,
                result: result
            });
        }
    });

    // Add subdocument failures
    saveResults.forEach((result, parentIndex) => {
        if (result.subdocument_results) {
            function collectFailedSubdocs(subdocResults, parentIdx) {
                subdocResults.forEach(subdoc => {
                    if (!subdoc.success) {
                        failedItems.push({
                            type: 'subdoc',
                            parentIndex: parentIdx,
                            path: subdoc.path,
                            cacheKey: subdoc.cache_key,
                            title: subdoc.title
                        });
                    }
                    if (subdoc.nested_subdocument_results) {
                        collectFailedSubdocs(subdoc.nested_subdocument_results, parentIdx);
                    }
                });
            }
            collectFailedSubdocs(result.subdocument_results, parentIndex);
        }
    });

    if (failedItems.length === 0) {
        showStatus('No failed saves to retry', 'info');
        return;
    }

    showLoading(`Retrying ${failedItems.length} failed saves...`);

    let successCount = 0;
    let failCount = 0;

    for (const item of failedItems) {
        try {
            if (item.type === 'main') {
                // Existing main document retry logic
                let itemData;
                if (item.result.originalData) {
                    itemData = item.result.originalData;
                } else {
                    const originalItem = extractedData.find(dataItem =>
                        dataItem.filename === item.result.filename && dataItem.status === FILE_STATUS.SUCCESS
                    );
                    if (!originalItem) {
                        failCount++;
                        continue;
                    }
                    itemData = {
                        ...originalItem.data,
                        filename: originalItem.filename,
                        file_index: originalItem.file_index,
                        manual_tags: originalItem.data.manual_tags || [],
                        auto_tags: originalItem.data.auto_tags || [],
                        file_key: originalItem.data.file_key,
                        session_id: originalItem.data.session_id || sessionId,
                        subdocument: originalItem.data.subdocument || [],
                        images: originalItem.data.images || []
                    };
                }

                const response = await fetch("{% url 'admin:chatbot_media_retry_save' %}", {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken,
                    },
                    body: JSON.stringify({
                        item_data: itemData,
                        company_bot_id: document.getElementById('companyBotSelect').value,
                        session_id: sessionId
                    })
                });

                const retryResult = await response.json();
                if (retryResult.success) {
                    saveResults[item.index] = {
                        ...retryResult.result,
                        originalData: itemData
                    };
                    successCount++;
                } else {
                    failCount++;
                }
            } else if (item.type === 'subdoc') {
                // Retry subdocument
                await retrySubdocSave(item.parentIndex, item.path, item.cacheKey);
                successCount++;
            }

            showLoading(`Retrying saves... ${successCount + failCount}/${failedItems.length} processed`);

        } catch (error) {
            failCount++;
            console.error(`Retry failed:`, error);
        }
    }

    hideLoading();
    displayResults(saveResults);

    if (successCount > 0 && failCount === 0) {
        showStatus(`Successfully retried all ${successCount} failed saves!`, 'success');
    } else if (successCount > 0 && failCount > 0) {
        showStatus(`Retried ${successCount} saves successfully, ${failCount} still failed.`, 'warning');
    } else {
        showStatus(`All ${failCount} retry attempts failed.`, 'error');
    }
}

async function retryExtraction(index) {
    const fileData = uploadedFiles[index];

    // Set status to processing
    uploadedFiles[index].status = FILE_STATUS.PROCESSING;
    uploadedFiles[index].error = null;
    uploadedFiles[index].errorTimestamp = null;
    updateFileList();

    try {
        const requestData = {
            file_data: {
                filename: fileData.name,
                file_index: index,
                file_key: fileData.fileKey,
                size: fileData.size
            },
            company_bot_id: document.getElementById('companyBotSelect').value,
            session_id: fileData.sessionId || sessionId
        };

        console.log('Retry request data:', requestData);

        const response = await fetch("{% url 'admin:chatbot_media_retry_extract' %}", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();
        if (result.success) {
            // Update the file status
            uploadedFiles[index].status = FILE_STATUS.SUCCESS;
            uploadedFiles[index].error = null;
            uploadedFiles[index].errorTimestamp = null;

            // Ensure organization is set
            if (!result.data.organization) {
                result.data.organization = userCompanyName || '';
            }
            if (!result.data.key_values) {
                result.data.key_values = [];
            }
            if (!result.data.key_values.some(kv => kv.key === 'ORGANIZATION')) {
                result.data.key_values.push({
                    key: 'ORGANIZATION',
                    value: result.data.organization
                });
            }

            // Update or add to extracted data
            const existingIndex = extractedData.findIndex(item => item && item.file_index === index);
            if (existingIndex >= 0) {
                extractedData[existingIndex] = {
                    id: `temp_${Date.now()}_${index}`,
                    filename: fileData.name,
                    file: fileData.file,
                    file_index: index,
                    status: FILE_STATUS.SUCCESS,
                    data: result.data
                };
            } else {
                extractedData.push({
                    id: `temp_${Date.now()}_${index}`,
                    filename: fileData.name,
                    file: fileData.file,
                    file_index: index,
                    status: FILE_STATUS.SUCCESS,
                    data: result.data
                });
            }

            // Check if AI task needs to be waited for
            if (result.data && result.data.auto_tag_task_id && !result.data.auto_tags_ready) {
                isWaitingForAI = true;
                document.getElementById('aiStatus').style.display = 'inline';

                try {
                    await waitForAllTasksToComplete([result.data.auto_tag_task_id]);
                } catch (error) {
                    console.error('AI enhancement error:', error);
                } finally {
                    isWaitingForAI = false;
                    document.getElementById('aiStatus').style.display = 'none';
                }
            }

            updateFileList();
            showStatus(`Successfully uploaded ${fileData.name}`, 'success');
        } else {
            uploadedFiles[index].status = FILE_STATUS.ERROR;
            uploadedFiles[index].error = result.error;
            uploadedFiles[index].errorTimestamp = new Date().toISOString();
            showStatus(`Upload failed for ${fileData.name}: ${result.error}`, 'error');
            updateFileList();
        }
    } catch (error) {
        uploadedFiles[index].status = FILE_STATUS.ERROR;
        uploadedFiles[index].error = error.message;
        uploadedFiles[index].errorTimestamp = new Date().toISOString();
        showStatus(`Upload failed for ${fileData.name}: ${error.message}`, 'error');
        updateFileList();
    } finally {
        updateFailedLinks();
    }
}

// Company bot selection
document.getElementById('companyBotSelect').addEventListener('change', updateFileList);

// Data upload via API
async function extractDataFromFiles(files) {
    const companyBotId = document.getElementById('companyBotSelect').value;
    const extractedItems = [];

    // Generate session ID if not exists
    if (!sessionId) {
        sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    // Process files one by one to show progress
    for (let i = 0; i < files.length; i++) {
        const fileData = files[i];
        const fileIndex = fileData.index;

        if (fileData.status === FILE_STATUS.SKIPPED) {
            // Add placeholder for skipped files
            extractedItems.push({
                id: `skipped_${fileIndex}`,
                filename: fileData.name,
                file: fileData.file,
                file_index: fileIndex,
                status: FILE_STATUS.SKIPPED,
                data: null
            });
            continue;
        }

        // Set status to processing
        uploadedFiles[fileIndex].status = FILE_STATUS.PROCESSING;
        updateFileList();

        try {
            // Create FormData for single file
            const formData = new FormData();
            formData.append('files', fileData.file);
            formData.append('file_indices', fileIndex);
            formData.append('company_bot_id', companyBotId);
            formData.append('session_id', sessionId);

            console.log(`Uploading file ${i + 1}/${files.length}: ${fileData.name} with index ${fileIndex}`);

            const response = await fetch("{% url 'admin:chatbot_media_batch_extract' %}", {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken,
                },
                body: formData
            });

            const result = await response.json();
            if (result.success && result.data.length > 0) {
                const uploadResult = result.data[0]; // Single file result

                // Store session_id from response
                if (result.session_id) {
                    sessionId = result.session_id;
                }

                if (uploadResult.status === 'success') {
                    uploadedFiles[fileIndex].status = FILE_STATUS.SUCCESS;
                    uploadedFiles[fileIndex].error = null;
                    uploadedFiles[fileIndex].errorTimestamp = null;
                    uploadedFiles[fileIndex].sessionId = sessionId;
                    uploadedFiles[fileIndex].fileKey = uploadResult.file_key;

                    // Ensure organization is set
                    uploadResult.organization = selectedOrganization ? selectedOrganization.name : (userCompanyName || '');
                    if (!uploadResult.key_values) {
                        uploadResult.key_values = [];
                    }
                    const orgKvIndex = uploadResult.key_values.findIndex(kv => kv.key === 'ORGANIZATION');
                    if (orgKvIndex >= 0) {
                        uploadResult.key_values[orgKvIndex].value = uploadResult.organization;
                    } else {
                        uploadResult.key_values.unshift({
                            key: 'ORGANIZATION',
                            value: uploadResult.organization,
                            source: 'ai'
                        });
                    }

                    extractedItems.push({
                        id: `temp_${Date.now()}_${fileIndex}`,
                        filename: fileData.name,
                        file: fileData.file,
                        file_index: fileIndex,
                        status: FILE_STATUS.SUCCESS,
                        data: uploadResult
                    });
                } else {
                    uploadedFiles[fileIndex].status = FILE_STATUS.ERROR;
                    uploadedFiles[fileIndex].error = uploadResult.error;
                    uploadedFiles[fileIndex].errorTimestamp = new Date().toISOString();
                    uploadedFiles[fileIndex].sessionId = sessionId;
                    uploadedFiles[fileIndex].fileKey = uploadResult.file_key;

                    extractedItems.push({
                        id: `error_${fileIndex}`,
                        filename: fileData.name,
                        file: fileData.file,
                        file_index: fileIndex,
                        status: FILE_STATUS.ERROR,
                        data: uploadResult,
                        error: uploadResult.error
                    });
                }
            } else {
                throw new Error(result.error || 'Failed to extract data');
            }
        } catch (error) {
            console.error(`Error processing file ${fileData.name}:`, error);

            uploadedFiles[fileIndex].status = FILE_STATUS.ERROR;
            uploadedFiles[fileIndex].error = error.message;
            uploadedFiles[fileIndex].errorTimestamp = new Date().toISOString();

            extractedItems.push({
                id: `error_${fileIndex}`,
                filename: fileData.name,
                file: fileData.file,
                file_index: fileIndex,
                status: FILE_STATUS.ERROR,
                data: null,
                error: error.message
            });
        }

        updateFileList();

        // Small delay to show progress
        await new Promise(resolve => setTimeout(resolve, 200));
    }

    return extractedItems;
}

function ensureSubdocumentOrganization(subdoc, parentOrg) {
    // Use selected organization instead of parent's extracted organization
    const orgToUse = selectedOrganization ? selectedOrganization.name : (parentOrg || userCompanyName || '');
    subdoc.organization = orgToUse;

    // Update or add organization in key-values
    if (!subdoc.key_values) {
        subdoc.key_values = [];
    }

    // Find existing ORGANIZATION key-value
    let orgKvIndex = subdoc.key_values.findIndex(kv => kv.key === 'ORGANIZATION');

    if (orgKvIndex >= 0) {
        // Update existing organization to selected value
        subdoc.key_values[orgKvIndex].value = subdoc.organization;
    } else {
        // Add organization key-value
        subdoc.key_values.unshift({
            key: 'ORGANIZATION',
            value: subdoc.organization
        });
    }

    // Process nested subdocuments recursively
    if (subdoc.subdocument && Array.isArray(subdoc.subdocument)) {
        subdoc.subdocument.forEach(nestedSub => {
            // Pass the same selected organization down
            ensureSubdocumentOrganization(nestedSub, subdoc.organization);
        });
    }
}

// Wait for all AI tasks to complete
async function waitForAllTasksToComplete(taskIds) {
    return new Promise((resolve, reject) => {
        const totalTasks = taskIds.length;
        let checkAttempts = 0;
        const maxAttempts = 300; // High limit to handle very long tasks
        let startTime = Date.now();

        const scheduleNextCheck = () => {
            // Calculate interval based on elapsed time
            const elapsedMinutes = (Date.now() - startTime) / (1000 * 60);
            const interval = elapsedMinutes < 2 ? 5000 : 30000; // 5s for first 2 min, then 30s

            setTimeout(async () => {
                checkAttempts++;

                try {
                    const response = await fetch("{% url 'admin:chatbot_media_task_status' %}", {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrftoken,
                        },
                        body: JSON.stringify({ task_ids: taskIds })
                    });

                    const result = await response.json();
                    if (result.success) {
                        let completedTasks = 0;

                        extractedData.forEach(item => {
                            if (item.status === FILE_STATUS.SUCCESS && item.data && item.data.auto_tag_task_id) {
                                const taskResult = result.results[item.data.auto_tag_task_id];

                                if (taskResult && taskResult.status === 'SUCCESS' && !item.data.auto_tags_ready) {
                                    // Process the enhanced AI data
                                    const aiResult = taskResult.result;

                                    // Update auto tags
                                    const autoTags = aiResult.auto_tags || [];
                                    item.data.auto_tags = autoTags.map(tag => {
                                        return typeof tag === 'object' ? tag.text : tag;
                                    });
                                    item.data.auto_tags_full = autoTags;
                                    item.data.auto_tags_ready = true;

                                    // Update enhanced data if available
                                    if (aiResult.enhanced_data) {
                                        const enhanced = aiResult.enhanced_data;

                                        if (enhanced.description) item.data.description = enhanced.description;
                                        if (enhanced.hasOwnProperty('extracted_text')) item.data.extracted_text = enhanced.extracted_text;
                                        if (enhanced.media_type) item.data.media_type = enhanced.media_type;

                                        if (enhanced.url && Array.isArray(enhanced.url)) {
                                            item.data.url = enhanced.url;
                                        }
                                        // Merge enhanced key-values with existing ones
                                        // Merge enhanced key-values with existing ones, but preserve user-selected organization
                                        if (enhanced.enhanced_key_values && enhanced.enhanced_key_values.length > 0) {
                                            const basicKVs = item.data.key_values.filter(kv =>
                                                kv.key === 'FILE TYPE' || kv.key === 'FILE SIZE'
                                            );

                                            // Filter out AI-extracted organization from enhanced key-values
                                            const enhancedKVsWithoutOrg = enhanced.enhanced_key_values.filter(kv => kv.key !== 'ORGANIZATION');

                                            // Keep user-selected organization
                                            const userSelectedOrg = selectedOrganization ? selectedOrganization.name : (userCompanyName || '');
                                            enhancedKVsWithoutOrg.unshift({
                                                key: 'ORGANIZATION',
                                                value: userSelectedOrg,
                                                source: 'ai'
                                            });

                                            item.data.key_values = [...basicKVs, ...enhancedKVsWithoutOrg];
                                        } else {
                                            // Ensure organization reflects user selection
                                            const userSelectedOrg = selectedOrganization ? selectedOrganization.name : (userCompanyName || '');
                                            if (!item.data.key_values.some(kv => kv.key === 'ORGANIZATION')) {
                                                item.data.key_values.push({
                                                    key: 'ORGANIZATION',
                                                    value: userSelectedOrg,
                                                    source: 'ai'
                                                });
                                            } else {
                                                // Update existing organization key-value to user selection
                                                const orgKvIndex = item.data.key_values.findIndex(kv => kv.key === 'ORGANIZATION');
                                                if (orgKvIndex >= 0) {
                                                    item.data.key_values[orgKvIndex].value = userSelectedOrg;
                                                }
                                            }
                                        }

                                        // Ensure main organization field reflects user selection, not AI extraction
                                        item.data.organization = selectedOrganization ? selectedOrganization.name : (userCompanyName || '');

                                       // Update subdocuments if available - FORCE user-selected organization
                                        if (enhanced.subdocument && Array.isArray(enhanced.subdocument)) {
                                            const userSelectedOrg = selectedOrganization ? selectedOrganization.name : (userCompanyName || '');

                                            enhanced.subdocument.forEach(subdoc => {
                                                ensureSubdocumentOrganization(subdoc, userSelectedOrg);
                                            });
                                            item.data.subdocument = enhanced.subdocument;
                                        }

                                        // Update images if available
                                        if (enhanced.images && Array.isArray(enhanced.images)) {
                                            item.data.images = enhanced.images;
                                        }
                                        if (enhanced.failed_links && Array.isArray(enhanced.failed_links)) {
                                            item.data.failed_links = enhanced.failed_links;
                                        }
                                        // Update source_documents if available
                                        if (enhanced.source_documents && Array.isArray(enhanced.source_documents)) {
                                            item.data.source_documents = enhanced.source_documents;
                                        }
                                    }

                                    console.log(`AI extraction completed for ${item.filename}:`, aiResult);
                                } else if (taskResult && (taskResult.status === 'FAILURE' || taskResult.status === 'ERROR') && !item.data.auto_tags_ready) {
                                    // *** CHANGED: Mark entire document as failed ***
                                    const errorMsg = taskResult.error || 'AI processing failed';

                                    // Find the corresponding file in uploadedFiles and mark as failed
                                    const fileIndex = uploadedFiles.findIndex(f => f.name === item.filename);
                                    if (fileIndex >= 0) {
                                        uploadedFiles[fileIndex].status = FILE_STATUS.ERROR;
                                        uploadedFiles[fileIndex].error = errorMsg;
                                        uploadedFiles[fileIndex].errorTimestamp = new Date().toISOString();
                                    }

                                    // Mark the extracted data item as failed
                                    item.status = FILE_STATUS.ERROR;
                                    item.error = errorMsg;

                                    // Remove from successful extractedData
                                    const extractedIndex = extractedData.findIndex(ed => ed.filename === item.filename);
                                    if (extractedIndex >= 0) {
                                        extractedData[extractedIndex].status = FILE_STATUS.ERROR;
                                        extractedData[extractedIndex].error = errorMsg;
                                    }

                                    console.error(`AI extraction failed for ${item.filename}:`, errorMsg);
                                }

                                if (item.data.auto_tags_ready || item.status === FILE_STATUS.ERROR) {
                                    completedTasks++;
                                }
                            }
                        });

                        updateFailedLinks();

                        // Update loading message with progress
                        showLoading(`AI extraction in progress... ${completedTasks}/${totalTasks} completed`);

                        // Check if all tasks are complete (including failed ones)
                        if (completedTasks >= totalTasks) {
                            console.log(`AI extraction finished. Completed: ${completedTasks}/${totalTasks} in ${checkAttempts} API calls`);
                            hideLoading();

                            // *** CHANGED: Update file list to show failed documents, no success message ***
                            updateFileList();
                            updateButtonStates();

                            setTimeout(() => {
                                resolve();
                            }, 100);
                            return;
                        }

                        // Check if we've exceeded max attempts
                        if (checkAttempts >= maxAttempts) {
                            console.warn(`AI extraction timed out after ${checkAttempts} attempts`);
                            hideLoading();

                            // *** CHANGED: Mark remaining tasks as failed due to timeout ***
                            extractedData.forEach(item => {
                                if (item.status === FILE_STATUS.SUCCESS && item.data && item.data.auto_tag_task_id && !item.data.auto_tags_ready) {
                                    const errorMsg = 'AI processing timed out';

                                    // Find the corresponding file in uploadedFiles and mark as failed
                                    const fileIndex = uploadedFiles.findIndex(f => f.name === item.filename);
                                    if (fileIndex >= 0) {
                                        uploadedFiles[fileIndex].status = FILE_STATUS.ERROR;
                                        uploadedFiles[fileIndex].error = errorMsg;
                                        uploadedFiles[fileIndex].errorTimestamp = new Date().toISOString();
                                    }

                                    // Mark the extracted data item as failed
                                    item.status = FILE_STATUS.ERROR;
                                    item.error = errorMsg;
                                }
                            });

                            updateFileList();
                            updateButtonStates();
                            resolve();
                            return;
                        }

                        // Schedule next check
                        scheduleNextCheck();
                    } else {
                        // *** CHANGED: Handle API call failures by marking as failed ***
                        console.error('API call failed:', result);
                        if (checkAttempts >= maxAttempts) {
                            hideLoading();

                            // Mark all pending AI tasks as failed
                            extractedData.forEach(item => {
                                if (item.status === FILE_STATUS.SUCCESS && item.data && item.data.auto_tag_task_id && !item.data.auto_tags_ready) {
                                    const errorMsg = 'AI processing failed to complete';

                                    // Find the corresponding file in uploadedFiles and mark as failed
                                    const fileIndex = uploadedFiles.findIndex(f => f.name === item.filename);
                                    if (fileIndex >= 0) {
                                        uploadedFiles[fileIndex].status = FILE_STATUS.ERROR;
                                        uploadedFiles[fileIndex].error = errorMsg;
                                        uploadedFiles[fileIndex].errorTimestamp = new Date().toISOString();
                                    }

                                    // Mark the extracted data item as failed
                                    item.status = FILE_STATUS.ERROR;
                                    item.error = errorMsg;
                                }
                            });

                            updateFileList();
                            updateButtonStates();
                            resolve();
                            return;
                        }
                        // Retry on API failure
                        scheduleNextCheck();
                    }
                } catch (error) {
                    console.error('Error checking task status:', error);
                    if (checkAttempts >= maxAttempts) {
                        hideLoading();

                        // *** CHANGED: Mark all pending AI tasks as failed ***
                        extractedData.forEach(item => {
                            if (item.status === FILE_STATUS.SUCCESS && item.data && item.data.auto_tag_task_id && !item.data.auto_tags_ready) {
                                const errorMsg = 'AI processing encountered an error';

                                // Find the corresponding file in uploadedFiles and mark as failed
                                const fileIndex = uploadedFiles.findIndex(f => f.name === item.filename);
                                if (fileIndex >= 0) {
                                    uploadedFiles[fileIndex].status = FILE_STATUS.ERROR;
                                    uploadedFiles[fileIndex].error = errorMsg;
                                    uploadedFiles[fileIndex].errorTimestamp = new Date().toISOString();
                                }

                                // Mark the extracted data item as failed
                                item.status = FILE_STATUS.ERROR;
                                item.error = errorMsg;
                            }
                        });

                        updateFileList();
                        updateButtonStates();
                        resolve();
                        return;
                    }
                    // Retry on error
                    scheduleNextCheck();
                }
            }, interval);
        };

        // Start the checking process
        scheduleNextCheck();

        // Overall safety timeout (2 hours)
        setTimeout(() => {
            console.warn('AI extraction timed out after 2 hours');
            hideLoading();

            // *** CHANGED: Mark all pending AI tasks as failed due to overall timeout ***
            extractedData.forEach(item => {
                if (item.status === FILE_STATUS.SUCCESS && item.data && item.data.auto_tag_task_id && !item.data.auto_tags_ready) {
                    const errorMsg = 'AI processing timed out after 2 hours';

                    // Find the corresponding file in uploadedFiles and mark as failed
                    const fileIndex = uploadedFiles.findIndex(f => f.name === item.filename);
                    if (fileIndex >= 0) {
                        uploadedFiles[fileIndex].status = FILE_STATUS.ERROR;
                        uploadedFiles[fileIndex].error = errorMsg;
                        uploadedFiles[fileIndex].errorTimestamp = new Date().toISOString();
                    }

                    // Mark the extracted data item as failed
                    item.status = FILE_STATUS.ERROR;
                    item.error = errorMsg;
                }
            });

            updateFileList();
            updateButtonStates();
            resolve();
        }, 7200000); // 2 hours
    });
}

// Proceed button handler
document.getElementById('proceedBtn').addEventListener('click', () => {
    // Filter out skipped files for pagination
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);

    if (validItems.length === 0) {
        showStatus('No files available for review. Please upload files first.', 'warning');
        return;
    }

    totalPages = Math.ceil(validItems.length / itemsPerPage);
    currentPage = 1;

    renderExtractedData();
    updateStepIndicator(2);
});


// Add this function to support recursive subdocument rendering
function renderNestedSubdocuments(subdocs, parentPath, baseParentIndex) {
    if (!subdocs || !Array.isArray(subdocs) || subdocs.length === 0) {
        return '';
    }

    return subdocs.map((subdoc, index) => {
        const currentPath = `${parentPath}_${index}`;
        return renderSubdocumentItemRecursive(subdoc, currentPath, baseParentIndex);
    }).join('');
}

function addTagFromDropdownByPath(path, tagValue) {
    if (!tagValue) return;

    const subdoc = getSubdocByPath(path);
    if (subdoc) {
        if (!subdoc.manual_tags) {
            subdoc.manual_tags = [];
        }

        if (!subdoc.manual_tags.includes(tagValue)) {
            subdoc.manual_tags.push(tagValue);
            subdoc.hasUnsavedChanges = true;

            // Add the tag element directly
            const container = document.getElementById(`manualTagsContainer_${path}`);
            if (container) {
                const newTag = document.createElement('span');
                newTag.className = 'tag manual';
                newTag.innerHTML = `
                    ${tagValue}
                    <span class="remove-tag" onclick="removeTagByPath('${path}', '${tagValue.replace(/'/g, "\\'")}', 'manual')">×</span>
                `;
                const wrapper = container.querySelector('.tag-input-wrapper');
                container.insertBefore(newTag, wrapper);
            }

            // Reset save button state
            const saveBtn = document.getElementById(`saveBtn_${path}`);
            if (saveBtn && saveBtn.classList.contains('saved')) {
                saveBtn.textContent = 'Save changes';
                saveBtn.classList.remove('saved');
            }
        }

        // Reset dropdown
        const dropdown = document.getElementById(`tagDropdown_${path}`);
        if (dropdown) {
            dropdown.value = '';
        }
    }
}

function toggleTagDropdown(identifier) {
    const dropdown = document.getElementById(`tagDropdownList_${identifier}`);
    if (!dropdown) return;

    const isVisible = dropdown.classList.contains('show');

    // Close all other tag dropdowns
    document.querySelectorAll('.dropdown-list').forEach(dl => {
        dl.classList.remove('show');
    });

    // Toggle current dropdown
    if (!isVisible) {
        dropdown.classList.add('show');
        // Show all options initially
        filterTagDropdown(identifier, '');
    }
}

function filterTagDropdown(identifier, searchTerm) {
    const dropdown = document.getElementById(`tagDropdownList_${identifier}`);
    if (!dropdown) return;

    const filteredTags = existingManualTags.filter(tag =>
        tag.toLowerCase().includes(searchTerm.toLowerCase())
    );

    if (filteredTags.length > 0) {
        dropdown.innerHTML = filteredTags.map(tag => {
            const escapedTag = tag.replace(/'/g, "\\'");
            return `
                <div class="dropdown-option" onclick="selectTagFromDropdown('${identifier}', '${escapedTag}')">
                    ${tag}
                </div>
            `;
        }).join('');
    } else if (searchTerm.trim()) {
        dropdown.innerHTML = `
            <div class="dropdown-option no-results">
                No matching tags found
            </div>
        `;
    } else {
        dropdown.innerHTML = existingManualTags.map(tag => {
            const escapedTag = tag.replace(/'/g, "\\'");
            return `
                <div class="dropdown-option" onclick="selectTagFromDropdown('${identifier}', '${escapedTag}')">
                    ${tag}
                </div>
            `;
        }).join('');
    }

    dropdown.classList.add('show');
}

function selectTagFromDropdown(identifier, tagValue) {
    // Close dropdown
    const dropdown = document.getElementById(`tagDropdownList_${identifier}`);
    const searchInput = dropdown.previousElementSibling;

    dropdown.classList.remove('show');
    searchInput.value = '';

    // Determine if this is a path (subdocument) or index (main item)
    if (identifier.includes('_')) {
        // This is a path for subdocument
        addTagFromDropdownByPath(identifier, tagValue);
    } else {
        // This is an index for main item
        addTagFromDropdown(parseInt(identifier), tagValue);
    }
}

function handleTagDropdownKeypress(event, identifier) {
    if (event.key === 'Enter') {
        event.preventDefault();
        const searchTerm = event.target.value.trim();
        const dropdown = document.getElementById(`tagDropdownList_${identifier}`);

        if (searchTerm) {
            // Check if exact match exists
            const exactMatch = existingManualTags.find(tag =>
                tag.toLowerCase() === searchTerm.toLowerCase()
            );

            if (exactMatch) {
                selectTagFromDropdown(identifier, exactMatch);
            } else {
                // Add as new tag
                dropdown.classList.remove('show');
                event.target.value = '';

                // Determine if this is a path (subdocument) or index (main item)
                if (identifier.includes('_')) {
                    // This is a path for subdocument
                    const subdoc = getSubdocByPath(identifier);
                    if (subdoc && searchTerm) {
                        if (!subdoc.manual_tags) {
                            subdoc.manual_tags = [];
                        }

                        if (!subdoc.manual_tags.includes(searchTerm)) {
                            subdoc.manual_tags.push(searchTerm);
                            subdoc.hasUnsavedChanges = true;

                            // Add the tag element directly
                            const container = document.getElementById(`manualTagsContainer_${identifier}`);
                            if (container) {
                                const newTag = document.createElement('span');
                                newTag.className = 'tag manual';
                                newTag.innerHTML = `
                                    ${searchTerm}
                                    <span class="remove-tag" onclick="removeTagByPath('${identifier}', '${searchTerm.replace(/'/g, "\\'")}', 'manual')">×</span>
                                `;
                                const wrapper = container.querySelector('.tag-input-wrapper');
                                container.insertBefore(newTag, wrapper);
                            }

                            // Reset save button state
                            const saveBtn = document.getElementById(`saveBtn_${identifier}`);
                            if (saveBtn && saveBtn.classList.contains('saved')) {
                                saveBtn.textContent = 'Save changes';
                                saveBtn.classList.remove('saved');
                            }
                        }
                    }
                } else {
                    // This is an index for main item
                    const itemIndex = parseInt(identifier);
                    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
                    const actualIndex = (currentPage - 1) * itemsPerPage;
                    const item = validItems[actualIndex];

                    if (item && searchTerm) {
                        if (!item.data.manual_tags) {
                            item.data.manual_tags = [];
                        }

                        if (!item.data.manual_tags.includes(searchTerm)) {
                            item.data.manual_tags.push(searchTerm);
                            item.hasUnsavedChanges = true;

                            // Add the tag element directly instead of re-rendering
                            const container = document.getElementById(`manualTagsContainer_${identifier}`);
                            if (container) {
                                const escapedTag = searchTerm.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                                const newTag = document.createElement('span');
                                newTag.className = 'tag manual';
                                newTag.innerHTML = `
                                    ${searchTerm}
                                    <span class="remove-tag" onclick="removeTag(${itemIndex}, '${escapedTag}', 'manual')">×</span>
                                `;
                                const wrapper = container.querySelector('.tag-input-wrapper');
                                container.insertBefore(newTag, wrapper);
                            }

                            // Reset save button state
                            const saveBtn = document.getElementById(`saveBtn_${identifier}`);
                            if (saveBtn && saveBtn.classList.contains('saved')) {
                                saveBtn.textContent = 'Save changes';
                                saveBtn.classList.remove('saved');
                            }
                        }
                    }
                }
            }
        }
    } else if (event.key === 'Escape') {
        // Close dropdown on escape
        const dropdown = document.getElementById(`tagDropdownList_${identifier}`);
        dropdown.classList.remove('show');
        event.target.blur();
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.custom-dropdown')) {
        document.querySelectorAll('.dropdown-list').forEach(dl => {
            dl.classList.remove('show');
        });
    }
});

function toggleSubdocumentDisplayMode(path, isChecked) {
    const subdoc = getSubdocByPath(path);
    if (subdoc) {
        // Set display_mode: AI_ONLY if checked, VISIBLE if unchecked
        subdoc.display_mode = isChecked ? 'ai_only' : 'visible';
        subdoc.hasUnsavedChanges = true;

        // Update UI to show the state
        const checkbox = document.getElementById(`displayModeCheckbox_${path}`);
        const label = document.getElementById(`displayModeLabel_${path}`);

        if (checkbox && label) {
            if (isChecked) {
                label.style.opacity = '0.6';
                label.style.textDecoration = 'none';
            } else {
                label.style.opacity = '1';
                label.style.textDecoration = 'none';
            }
        }

        // Reset save button state
        const saveBtn = document.getElementById(`saveBtn_${path}`);
        if (saveBtn && saveBtn.classList.contains('saved')) {
            saveBtn.textContent = 'Save changes';
            saveBtn.classList.remove('saved');
        }

        console.log(`Display mode for ${path} set to:`, subdoc.display_mode);
    }
}

function renderSubdocumentItemRecursive(subdoc, path, baseParentIndex) {
    const subdocId = `subdoc_${path}`;

    // Initialize subdoc data structures if missing
    if (!subdoc.media_type) subdoc.media_type = 'text/plain';
    if (!subdoc.description) subdoc.description = subdoc.summary || '';
    if (!subdoc.key_values) subdoc.key_values = [];
    if (!subdoc.manual_tags) subdoc.manual_tags = [];
    if (!subdoc.auto_tags) {
        if (subdoc.tags && Array.isArray(subdoc.tags)) {
            subdoc.auto_tags = subdoc.tags.map(tag => {
                if (typeof tag === 'object' && tag.text) {
                    return tag.text;
                } else if (typeof tag === 'string') {
                    return tag;
                }
                return '';
            }).filter(tag => tag);
        } else {
            subdoc.auto_tags = [];
        }
    }

    // Initialize display_mode if not set
    if (!subdoc.display_mode) {
        subdoc.display_mode = 'visible';
    }

    // Check if subdocument was manually saved
    const saveButtonText = (subdoc.manuallySaved && !subdoc.hasUnsavedChanges) ? '✓ Saved' : 'Save changes';
    const saveButtonClass = (subdoc.manuallySaved && !subdoc.hasUnsavedChanges) ? 'btn btn-save saved' : 'btn btn-save';

    // Generate tags HTML
    const manualTagsHtml = subdoc.manual_tags.map(tag => {
        let tagText = typeof tag === 'object' && tag.text ? tag.text : tag;
        const escapedTagText = tagText.replace(/'/g, "\\'").replace(/"/g, '&quot;');

        return `
            <span class="tag manual">
                ${tagText}
                <span class="remove-tag" onclick="removeTagByPath('${path}', '${escapedTagText}', 'manual')">×</span>
            </span>
        `;
    }).join('');

    const autoTagsHtml = subdoc.auto_tags.map(tag => {
        let tagText = '';
        if (typeof tag === 'object' && tag.text) {
            tagText = tag.text;
        } else if (typeof tag === 'string') {
            tagText = tag;
        }
        const escapedTagText = tagText.replace(/'/g, "\\'").replace(/"/g, '&quot;');

        return `
            <span class="tag auto">
                ${tagText}
                <span class="remove-tag" onclick="removeTagByPath('${path}', '${escapedTagText}', 'auto')">×</span>
            </span>
        `;
    }).join('');

    // Generate key-values HTML with document type dropdown support
    const kvHtml = updateKeyValueHtmlWithDocTypeDropdown(subdoc, path);

    // Generate images HTML
    let imagesHtml = '';
    if (subdoc.images && subdoc.images.length > 0) {
        const imagesGridHtml = subdoc.images.map((img, imgIndex) => {
            let imgSrc = img.base64;
            if (imgSrc && !imgSrc.startsWith('data:')) {
                if (imgSrc.match(/^[A-Za-z0-9+/]+=*$/)) {
                    imgSrc = `data:image/${img.format || 'png'};base64,${imgSrc}`;
                }
            }

            return `
                <div class="image-item">
                    <img src="${imgSrc}" alt="Image ${imgIndex + 1}" class="image-preview"
                         onclick="event.stopPropagation(); openImageModal('${imgSrc}')"
                         onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                    <div style="display:none; padding: 20px; background: #f5f5f5; text-align: center;">
                        Image failed to load
                    </div>
                    <div class="image-info">
                        ${img.page ? `<div class="image-page">Page ${img.page}</div>` : ''}
                        ${img.width && img.height ? `<div>${img.width}x${img.height}</div>` : ''}
                    </div>
                    <button class="remove-image-btn" onclick="removeImageByPath('${path}', ${imgIndex})">Remove</button>
                </div>
            `;
        }).join('');

        imagesHtml = `
            <div class="images-section">
                <div class="images-header">Images (${subdoc.images.length})</div>
                <div class="images-grid">
                    ${imagesGridHtml}
                </div>
            </div>
        `;
    }

    // Recursively render nested subdocuments
    let nestedSubdocsHtml = '';
    if (subdoc.subdocument && Array.isArray(subdoc.subdocument) && subdoc.subdocument.length > 0) {
        nestedSubdocsHtml = `
            <div class="subdocuments-section" style="margin-left: 20px;">
                <div class="subdocuments-header">
                    Nested Subdocuments
                    <span class="subdocument-count">(${subdoc.subdocument.length})</span>
                </div>
                ${renderNestedSubdocuments(subdoc.subdocument, path, baseParentIndex)}
            </div>
        `;
    }

    const depth = path.split('_').length - 1;
    let title = subdoc.title || `Subdocument Level ${depth}`;

    // Add special handling for link subdocuments
    if (subdoc.document_type === 'linked_document' && subdoc.url && subdoc.url.length > 0) {
        title = `📎 ${subdoc.url[0]}`;
    }

    const isAiOnly = subdoc.display_mode === 'ai_only';

    // Check if subdocument is an Excel file by extension or media type
    const excelMediaTypes = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'application/vnd.google-apps.spreadsheet'
    ];
    const isSubdocExcelByType = subdoc.media_type && excelMediaTypes.includes(subdoc.media_type);
    const isSubdocExcelByUrl = (subdoc.file_url && (subdoc.file_url.toLowerCase().endsWith('.xlsx') || subdoc.file_url.toLowerCase().endsWith('.xls'))) ||
                               (subdoc.url && subdoc.url.length > 0 && (subdoc.url[0].toLowerCase().endsWith('.xlsx') || subdoc.url[0].toLowerCase().endsWith('.xls')));
    const isSubdocExcel = isSubdocExcelByType || isSubdocExcelByUrl;

    const subdocMarkdownHtml = isSubdocExcel ? `
                <div class="field-group">
                    <label>Markdown Content</label>
                    <textarea class="editable-field" id="extracted_text_${path}"
                       onchange="saveFieldByPath('${path}', 'extracted_text', this.value)" style="min-height: 150px;">${subdoc.extracted_text || ''}
                    </textarea>
                </div>
    ` : '';

    return `
        <div class="subdocument-item" id="${subdocId}" style="margin-left: ${(depth - 1) * 20}px;">
            <div class="subdocument-header" onclick="toggleSubdocumentByPath('${path}')">
                <div class="subdocument-title">
                    ${subdoc.document_type === 'linked_document' ? '🔗 ' : ''}${title}
                </div>
                <div class="subdocument-controls">
                    <div style="display: flex; align-items: center; gap: 10px; margin-right: 10px;">
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; margin: 0; user-select: none; font-size: 13px; color: #555;">
                            <input type="checkbox"
                                   id="displayModeCheckbox_${path}"
                                   ${isAiOnly ? 'checked' : ''}
                                   onclick="event.stopPropagation(); toggleSubdocumentDisplayMode('${path}', this.checked)"
                                   style="cursor: pointer;">
                            <span id="displayModeLabel_${path}" style="">
                                Do not Display (Use for AI alone)
                            </span>
                        </label>
                    </div>
                    <button class="remove-subdoc-btn" onclick="event.stopPropagation(); removeSubdocumentByPath('${path}')" style="margin-right: 8px;">Remove</button>
                    <svg class="expand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="m6 9 6 6 6-6"/>
                    </svg>
                </div>
            </div>
            <div class="subdocument-content">
                ${subdoc.document_type === 'linked_document' && subdoc.url ? `
                    <div class="field-group">
                        <label>Document URL</label>
                        <div style="padding: 10px; background-color: #f5f5f5; border-radius: 4px; word-break: break-all;">
                            <a href="${subdoc.url[0]}" target="_blank" style="color: #417690; text-decoration: none;">
                                ${subdoc.url[0]}
                            </a>
                        </div>
                    </div>
                    ${subdoc.source_document ? `
                        <div class="field-group">
                            <label>Found In</label>
                            <div style="padding: 10px; background-color: #f5f5f5; border-radius: 4px;">
                                ${subdoc.source_document}
                            </div>
                        </div>
                    ` : ''}
                ` : ''}

                <div class="field-group">
                    <label>Resource Type</label>
                    <select id="mediaType_${path}" onchange="saveFieldByPath('${path}', 'media_type', this.value)">
                        ${mediaTypesJS.map(mt =>
                            `<option value="${mt.value}" ${subdoc.media_type === mt.value ? 'selected' : ''}>${mt.label}</option>`
                        ).join('')}
                    </select>
                </div>

                <div class="field-group">
                    <label>Summary</label>
                    <textarea class="editable-field" id="description_${path}"
                       onchange="saveFieldByPath('${path}', 'description', this.value)">${subdoc.description || ''}
                    </textarea>
                </div>

                ${subdocMarkdownHtml}

                <div class="field-group">
                    <label>Tags</label>
                    <div class="tags-section">
                        <div class="tags-subsection">
                            <h4>Manual Tags</h4>
                            <div class="tags-input" id="manualTagsContainer_${path}">
                                ${manualTagsHtml}
                                <div class="tag-input-wrapper">
                                    <div class="custom-dropdown" id="customTagDropdown_${path}">
                                        <input type="text"
                                               class="dropdown-search"
                                               placeholder="Search or add tag..."
                                               onclick="toggleTagDropdown('${path}')"
                                               oninput="filterTagDropdown('${path}', this.value)"
                                               onkeypress="handleTagDropdownKeypress(event, '${path}')">
                                        <div class="dropdown-list" id="tagDropdownList_${path}">
                                            ${existingManualTags.map(tag => `
                                                <div class="dropdown-option" onclick="selectTagFromDropdown('${path}', '${tag.replace(/'/g, "\\'")}')">
                                                    ${tag}
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="tags-subsection">
                            <h4>Auto Tags</h4>
                            <div class="tags-input" id="autoTagsContainer_${path}">
                                ${autoTagsHtml}
                            </div>
                        </div>
                    </div>
                </div>

                <div class="field-group">
                    <label>Sections</label>
                    <div class="key-values" id="kvContainer_${path}">
                        ${kvHtml}
                    </div>
                    <button class="add-kv-btn" onclick="addKeyValueByPath('${path}')">Add Field</button>
                </div>

                ${imagesHtml}
                ${nestedSubdocsHtml}

                <div style="margin-top: 20px; text-align: right;">
                    <button class="${saveButtonClass}" id="saveBtn_${path}"
                            onclick="saveByPath('${path}', ${baseParentIndex})">${saveButtonText}</button>
                </div>
            </div>
        </div>
    `;
}

// Add these helper functions to handle path-based operations
function toggleSubdocumentByPath(path) {
    const subdocId = `subdoc_${path}`;
    const header = document.querySelector(`#${subdocId} .subdocument-header`);
    const content = document.querySelector(`#${subdocId} .subdocument-content`);

    if (!header || !content) return;

    if (header.classList.contains('expanded')) {
        header.classList.remove('expanded');
        content.classList.remove('show');
        expandedSubdocumentPaths.delete(path); // Remove from tracking
    } else {
        // Close any previously expanded subdocument at the same level
        const currentLevel = path.split('_').length;
        document.querySelectorAll('.subdocument-header.expanded').forEach(h => {
            const otherId = h.parentElement.id;
            const otherPath = otherId.replace('subdoc_', '');
            const otherLevel = otherPath.split('_').length;
            if (otherLevel === currentLevel) {
                h.classList.remove('expanded');
                h.nextElementSibling.classList.remove('show');
                expandedSubdocumentPaths.delete(otherPath); // Remove from tracking
            }
        });

        header.classList.add('expanded');
        content.classList.add('show');
        expandedSubdocumentPaths.add(path); // Add to tracking
    }
}

function restoreExpandedStates() {
    expandedSubdocumentPaths.forEach(path => {
        const subdocId = `subdoc_${path}`;
        const header = document.querySelector(`#${subdocId} .subdocument-header`);
        const content = document.querySelector(`#${subdocId} .subdocument-content`);

        if (header && content) {
            header.classList.add('expanded');
            content.classList.add('show');
        }
    });
}

// Helper function to get subdocument by path
function getSubdocByPath(path) {
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (!item) return null;

    const pathParts = path.split('_');
    let current = item.data;

    for (let i = 1; i < pathParts.length; i++) {
        const index = parseInt(pathParts[i]);
        if (current.subdocument && current.subdocument[index]) {
            current = current.subdocument[index];
        } else {
            return null;
        }
    }

    return current;
}

// Path-based save field function
function saveFieldByPath(path, field, value) {
    const subdoc = getSubdocByPath(path);
    if (subdoc) {
        subdoc[field] = value;
        subdoc.hasUnsavedChanges = true;

        // Reset save button state
        const saveBtn = document.getElementById(`saveBtn_${path}`);
        if (saveBtn && saveBtn.classList.contains('saved')) {
            saveBtn.textContent = 'Save changes';
            saveBtn.classList.remove('saved');
        }
    }
}

// Path-based save key-value function
function saveKeyValueByPath(path, kvIndex, field, value) {
    const subdoc = getSubdocByPath(path);
    if (subdoc && subdoc.key_values && subdoc.key_values[kvIndex]) {
        const keyName = subdoc.key_values[kvIndex].key;

        // Process the value based on whether it should be an array or string
        let processedValue = value;
        if (field === 'value') {
            const targetItem = { data: subdoc };

            if (shouldPreserveAsArray(value, keyName, targetItem)) {
                // Keep as formatted string for now, will be converted to array in collectFormData
                processedValue = value;
            } else {
                // Process as regular formatted content
                processedValue = processFormattedContentEnhanced(value, true, targetItem, keyName);
            }
        } else {
            processedValue = value;
        }

        subdoc.key_values[kvIndex][field] = processedValue;
        subdoc.hasUnsavedChanges = true;

        const saveBtn = document.getElementById(`saveBtn_${path}`);
        if (saveBtn && saveBtn.classList.contains('saved')) {
            saveBtn.textContent = 'Save changes';
            saveBtn.classList.remove('saved');
        }
    }
}

// Path-based remove tag function
function removeTagByPath(path, tag, tagType) {
    const subdoc = getSubdocByPath(path);
    if (subdoc) {
        const tagArray = tagType === 'manual' ? 'manual_tags' : 'auto_tags';
        if (subdoc[tagArray]) {
            const tagIndex = subdoc[tagArray].indexOf(tag);
            if (tagIndex > -1) {
                subdoc[tagArray].splice(tagIndex, 1);
                subdoc.hasUnsavedChanges = true;

                // Instead of re-rendering, just remove the tag element
                const container = document.getElementById(`${tagType}TagsContainer_${path}`);
                if (container) {
                    const tags = container.querySelectorAll('.tag');
                    tags.forEach(tagEl => {
                        const tagText = tagEl.textContent.trim().replace('×', '').trim();
                        if (tagText === tag) {
                            tagEl.remove();
                        }
                    });
                }

                // Reset save button state
                const saveBtn = document.getElementById(`saveBtn_${path}`);
                if (saveBtn && saveBtn.classList.contains('saved')) {
                    saveBtn.textContent = 'Save changes';
                    saveBtn.classList.remove('saved');
                }
            }
        }
    }
}

// Path-based handle tag input
function handleTagInputByPath(event, path, tagType) {
    if (event.key === 'Enter') {
        event.preventDefault();
        const input = event.target;
        const tag = input.value.trim();

        const subdoc = getSubdocByPath(path);
        if (subdoc && tag) {
            const tagArray = tagType === 'manual' ? 'manual_tags' : 'auto_tags';
            if (!subdoc[tagArray]) {
                subdoc[tagArray] = [];
            }

            if (!subdoc[tagArray].includes(tag)) {
                subdoc[tagArray].push(tag);
                subdoc.hasUnsavedChanges = true;

                // Add the tag element directly instead of re-rendering
                const container = document.getElementById(`${tagType}TagsContainer_${path}`);
                if (container) {
                    const newTag = document.createElement('span');
                    newTag.className = `tag ${tagType}`;
                    newTag.innerHTML = `
                        ${tag}
                        <span class="remove-tag" onclick="removeTagByPath('${path}', '${tag.replace(/'/g, "\\'")}', '${tagType}')">×</span>
                    `;
                    container.insertBefore(newTag, input);
                    input.value = '';
                }

                // Reset save button state
                const saveBtn = document.getElementById(`saveBtn_${path}`);
                if (saveBtn && saveBtn.classList.contains('saved')) {
                    saveBtn.textContent = 'Save changes';
                    saveBtn.classList.remove('saved');
                }
            }
        }
    }
}

// Path-based remove key-value function
function removeKeyValueByPath(path, kvIndex) {
    if (!confirm('Are you sure you want to remove this section?')) {
        return;
    }
    const subdoc = getSubdocByPath(path);
    if (subdoc && subdoc.key_values) {
        // Ensure we're removing the correct index
        if (kvIndex >= 0 && kvIndex < subdoc.key_values.length) {
            subdoc.key_values.splice(kvIndex, 1);
            subdoc.hasUnsavedChanges = true;

            // Update DOM directly instead of re-rendering
            const kvContainer = document.getElementById(`kvContainer_${path}`);
            if (kvContainer) {
                const kvPairs = kvContainer.querySelectorAll('.key-value-pair');
                if (kvPairs[kvIndex]) {
                    kvPairs[kvIndex].remove();

                    // Re-index remaining key-value pairs
                    const remainingPairs = kvContainer.querySelectorAll('.key-value-pair');
                    remainingPairs.forEach((pair, newIndex) => {
                        // Update IDs and event handlers
                        const keyInput = pair.querySelector('input[type="text"]');
                        const valueTextarea = pair.querySelector('textarea');
                        const removeBtn = pair.querySelector('.remove-kv-btn');

                        if (keyInput) {
                            keyInput.id = `key_${path}_${newIndex}`;
                            keyInput.setAttribute('onchange', `saveKeyValueByPath('${path}', ${newIndex}, 'key', this.value)`);
                        }
                        if (valueTextarea) {
                            valueTextarea.id = `value_${path}_${newIndex}`;
                            valueTextarea.setAttribute('onchange', `saveKeyValueByPath('${path}', ${newIndex}, 'value', this.value)`);
                        }
                        if (removeBtn) {
                            removeBtn.setAttribute('onclick', `removeKeyValueByPath('${path}', ${newIndex})`);
                        }
                    });
                }
            }

            // Reset save button state
            const saveBtn = document.getElementById(`saveBtn_${path}`);
            if (saveBtn && saveBtn.classList.contains('saved')) {
                saveBtn.textContent = 'Save changes';
                saveBtn.classList.remove('saved');
            }
        }
    }
}

// Path-based add key-value function
function addKeyValueByPath(path) {
    const subdoc = getSubdocByPath(path);
    if (subdoc) {
        if (!subdoc.key_values) {
            subdoc.key_values = [];
        }

        const newIndex = subdoc.key_values.length;
        subdoc.key_values.push({
            key: '',
            value: '',
            source: 'user', // Mark as user-added
            original_type: 'string'
        });
        subdoc.hasUnsavedChanges = true;

        // Add to DOM directly
        const kvContainer = document.getElementById(`kvContainer_${path}`);
        if (kvContainer) {
            const newKvPair = document.createElement('div');
            newKvPair.className = 'key-value-pair structured-content-kv';
            newKvPair.innerHTML = `
                <input type="text"
                       class="kv-key-input"
                       value=""
                       id="key_${path}_${newIndex}"
                       placeholder="Key"
                       onchange="saveKeyValueByPath('${path}', ${newIndex}, 'key', this.value)">
                <textarea class="key-value-textarea"
                          id="value_${path}_${newIndex}"
                          placeholder="Value"
                          onchange="saveKeyValueByPath('${path}', ${newIndex}, 'value', this.value)"
                          oninput="autoResizeTextarea(this)"></textarea>
                <button class="remove-kv-btn" onclick="removeKeyValueByPath('${path}', ${newIndex})">Remove</button>
            `;
            kvContainer.appendChild(newKvPair);
        }

        // Reset save button state
        const saveBtn = document.getElementById(`saveBtn_${path}`);
        if (saveBtn && saveBtn.classList.contains('saved')) {
            saveBtn.textContent = 'Save changes';
            saveBtn.classList.remove('saved');
        }
    }
}

// Path-based remove subdocument function
function removeSubdocumentByPath(path) {
    if (!confirm('Are you sure you want to remove this subdocument?')) {
        return;
    }
    const pathParts = path.split('_');
    if (pathParts.length < 2) return;

    // Get parent path and index
    const childIndex = parseInt(pathParts[pathParts.length - 1]);
    const parentPath = pathParts.slice(0, -1).join('_');

    const parent = parentPath === pathParts[0] ?
        getSubdocByPath(parentPath) :
        getSubdocByPath(parentPath);

    if (parent && parent.subdocument) {
        parent.subdocument.splice(childIndex, 1);
        parent.hasUnsavedChanges = true;
        renderExtractedData();
    }
}

// Path-based remove image function
function removeImageByPath(path, imageIndex) {
    if (!confirm('Are you sure you want to remove this image?')) {
        return;
    }
    const subdoc = getSubdocByPath(path);
    if (subdoc && subdoc.images) {
        subdoc.images.splice(imageIndex, 1);
        subdoc.hasUnsavedChanges = true;
        renderExtractedData();
    }
}

// Path-based save function
function saveByPath(path, baseParentIndex) {
    const saveBtn = document.getElementById(`saveBtn_${path}`);
    if (!saveBtn) return;

    const originalText = saveBtn.textContent;
    const subdoc = getSubdocByPath(path);

    if (subdoc) {
        // Collect data from form
        subdoc.media_type = document.getElementById(`mediaType_${path}`).value;
        subdoc.description = document.getElementById(`description_${path}`).value;

        // Save manual tags
        subdoc.manual_tags = [];
        const manualTagsContainer = document.getElementById(`manualTagsContainer_${path}`);
        if (manualTagsContainer) {
            const manualTags = manualTagsContainer.querySelectorAll('.tag.manual');
            manualTags.forEach(tag => {
                const tagText = tag.textContent.trim().replace('×', '').trim();
                if (tagText) subdoc.manual_tags.push(tagText);
            });
        }

        // Save auto tags
        subdoc.auto_tags = [];
        const autoTagsContainer = document.getElementById(`autoTagsContainer_${path}`);
        if (autoTagsContainer) {
            const autoTags = autoTagsContainer.querySelectorAll('.tag.auto');
            autoTags.forEach(tag => {
                const tagText = tag.textContent.trim().replace('×', '').trim();
                if (tagText) subdoc.auto_tags.push(tagText);
            });
        }

        // Save key-value pairs
        subdoc.key_values = [];
        const kvContainer = document.getElementById(`kvContainer_${path}`);
        if (kvContainer) {
            const kvPairs = kvContainer.querySelectorAll('.key-value-pair');
            kvPairs.forEach((pair) => {
                const keyInput = pair.querySelector(`input[id^="key_${path}_"]`);
                const valueTextarea = pair.querySelector(`textarea[id^="value_${path}_"]`);
                if (keyInput && valueTextarea) {
                    const key = keyInput.value;
                    const value = valueTextarea.value;
                    if (key || value) {
                        subdoc.key_values.push({ key, value });
                    }
                }
            });
        }

        // Mark as saved
        subdoc.manuallySaved = true;
        subdoc.savedAt = new Date().toISOString();
        subdoc.hasUnsavedChanges = false;

        // Update button
        saveBtn.textContent = '✓ Saved';
        saveBtn.classList.add('saved');
        saveBtn.disabled = false;

        resetSaveButtonAfterTimeout(`saveBtn_${path}`, 3000);

        console.log(`Saved subdocument at path ${path}:`, subdoc);
    }
}

// Save all files at once
function saveAllFiles() {
    // Save current page first
    const currentIndex = (currentPage - 1) * itemsPerPage;
    saveCurrentFile(currentIndex);

    // Mark all valid items as saved
    extractedData.forEach((item, index) => {
        if (item && item.status === FILE_STATUS.SUCCESS) {
            item.manuallySaved = true;
            item.savedAt = new Date().toISOString();
        }
    });

    showStatus('All valid files have been saved!', 'success');
    console.log('All files saved:', extractedData);
}

// Manual save for current file
function saveCurrentFile(index, isSubdoc = false, parentIndex = null, subdocIndex = null) {
    const saveBtn = isSubdoc ?
        document.getElementById(`saveBtn_subdoc_${parentIndex}_${subdocIndex}`) :
        document.getElementById(`saveBtn_${index}`);
    if (!saveBtn) return;

    const originalText = saveBtn.textContent;

    // Find the actual item in extractedData
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            // Save subdocument data
            const subdoc = item.data.subdocument[subdocIndex];
            subdoc.media_type = document.getElementById(`mediaType_subdoc_${parentIndex}_${subdocIndex}`).value;
            subdoc.description = document.getElementById(`description_subdoc_${parentIndex}_${subdocIndex}`).value;

            // Save manual tags
            subdoc.manual_tags = [];
            const manualTagsContainer = document.getElementById(`manualTagsContainer_subdoc_${parentIndex}_${subdocIndex}`);
            if (manualTagsContainer) {
                const manualTags = manualTagsContainer.querySelectorAll('.tag.manual');
                manualTags.forEach(tag => {
                    const tagText = tag.textContent.trim().replace('×', '').trim();
                    if (tagText) subdoc.manual_tags.push(tagText);
                });
            }

            // Save auto tags
            subdoc.auto_tags = [];
            const autoTagsContainer = document.getElementById(`autoTagsContainer_subdoc_${parentIndex}_${subdocIndex}`);
            if (autoTagsContainer) {
                const autoTags = autoTagsContainer.querySelectorAll('.tag.auto');
                autoTags.forEach(tag => {
                    const tagText = tag.textContent.trim().replace('×', '').trim();
                    if (tagText) subdoc.auto_tags.push(tagText);
                });
            }

            // Save key-value pairs
            subdoc.key_values = [];
            const kvContainer = document.getElementById(`kvContainer_subdoc_${parentIndex}_${subdocIndex}`);
            if (kvContainer) {
                const kvPairs = kvContainer.querySelectorAll('.key-value-pair');
                kvPairs.forEach((pair) => {
                    const keyInput = pair.querySelector(`input[id^="key_subdoc_"]`);
                    const valueInput = pair.querySelector(`input[id^="value_subdoc_"]`);
                    if (keyInput && valueInput) {
                        const key = keyInput.value;
                        const value = valueInput.value;
                        if (key || value) {
                            subdoc.key_values.push({ key, value });
                        }
                    }
                });
            }

            // Mark subdocument as saved
            subdoc.manuallySaved = true;
            subdoc.savedAt = new Date().toISOString();
            subdoc.hasUnsavedChanges = false;
        } else {
            // Save main document data
            item.data.media_type = document.getElementById(`mediaType_${index}`).value;
            item.data.description = document.getElementById(`description_${index}`).value;

            // Save manual tags
            item.data.manual_tags = [];
            const manualTagsContainer = document.getElementById(`manualTagsContainer_${index}`);
            if (manualTagsContainer) {
                const manualTags = manualTagsContainer.querySelectorAll('.tag.manual');
                manualTags.forEach(tag => {
                    const tagText = tag.textContent.trim().replace('×', '').trim();
                    if (tagText) item.data.manual_tags.push(tagText);
                });
            }

            // Save auto tags
            item.data.auto_tags = [];
            const autoTagsContainer = document.getElementById(`autoTagsContainer_${index}`);
            if (autoTagsContainer) {
                const autoTags = autoTagsContainer.querySelectorAll('.tag.auto');
                autoTags.forEach(tag => {
                    const tagText = tag.textContent.trim().replace('×', '').trim();
                    if (tagText) item.data.auto_tags.push(tagText);
                });
            }

            // Save key-value pairs
            item.data.key_values = [];
            const kvContainer = document.getElementById(`kvContainer_${index}`);
            if (kvContainer) {
                const kvPairs = kvContainer.querySelectorAll('.key-value-pair');
                kvPairs.forEach((pair, kvIndex) => {
                    const keyInput = pair.querySelector(`input[id^="key_"]`);
                    const valueTextarea = pair.querySelector(`textarea[id^="value_"]`); // Changed to textarea
                    if (keyInput && valueTextarea) {
                        const key = keyInput.value;
                        const value = valueTextarea.value;
                        if (key || value) {
                            item.data.key_values.push({ key, value });
                        }
                    }
                });
            }

            // Mark this item as manually saved
            item.manuallySaved = true;
            item.savedAt = new Date().toISOString();
            item.hasUnsavedChanges = false;
        }

        // Update button to show saved state
        saveBtn.textContent = '✓ Saved';
        saveBtn.disabled = false;

        // Reset button after 3 seconds
        setTimeout(() => {
            saveBtn.textContent = originalText;
            saveBtn.classList.remove('saved');
        }, 3000);

        resetSaveButtonAfterTimeout(isSubdoc ? `saveBtn_subdoc_${parentIndex}_${subdocIndex}` : `saveBtn_${index}`, 3000);

        console.log(`Manually saved ${isSubdoc ? 'subdocument' : 'file'} ${index}:`, item.data);
    }
}

function resetSaveButtonAfterTimeout(buttonId, delay = 3000) {
    const saveBtn = document.getElementById(buttonId);
    if (!saveBtn) return;

    // Clear any existing timeout for this button
    if (saveBtn.resetTimeout) {
        clearTimeout(saveBtn.resetTimeout);
    }

    // Set new timeout
    saveBtn.resetTimeout = setTimeout(() => {
        saveBtn.textContent = 'Save current changes';
        saveBtn.classList.remove('saved');
        saveBtn.disabled = false;
    }, delay);
}

// Save field data with timer
function saveFieldData(index, field, value, isSubdoc = false, parentIndex = null, subdocIndex = null) {
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            // Update subdocument field
            item.data.subdocument[subdocIndex][field] = value;
            item.data.subdocument[subdocIndex].hasUnsavedChanges = true;

            // Reset save button state
            const saveBtn = document.getElementById(`saveBtn_subdoc_${parentIndex}_${subdocIndex}`);
            if (saveBtn) {
                // Clear any existing timeout
                if (saveBtn.resetTimeout) {
                    clearTimeout(saveBtn.resetTimeout);
                }
                saveBtn.textContent = 'Save current changes';
                saveBtn.classList.remove('saved');
                saveBtn.disabled = false;
            }
        } else if (!isSubdoc && item.data) {
            // Update main document field
            item.data[field] = value;
            item.hasUnsavedChanges = true;

            // Reset save button state when changes are made
            const saveBtn = document.getElementById(`saveBtn_${index}`);
            if (saveBtn) {
                // Clear any existing timeout
                if (saveBtn.resetTimeout) {
                    clearTimeout(saveBtn.resetTimeout);
                }
                saveBtn.textContent = 'Save current changes';
                saveBtn.classList.remove('saved');
                saveBtn.disabled = false;
            }
        }

        console.log(`Saved ${field} for ${isSubdoc ? 'subdocument' : 'item'} ${index}:`, value);
    }
}

// Save key-value data
function saveKeyValueData(index, kvIndex, field, value, isSubdoc = false, parentIndex = null, subdocIndex = null) {
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        let targetData;
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            targetData = item.data.subdocument[subdocIndex];
        } else if (!isSubdoc && item.data) {
            targetData = item.data;
        }

        if (targetData && targetData.key_values && targetData.key_values[kvIndex]) {
            const keyName = targetData.key_values[kvIndex].key;

            // Process the value based on whether it should be an array or string
            let processedValue = value;
            if (field === 'value') {
                const targetItem = isSubdoc ? { data: targetData } : item;

                if (shouldPreserveAsArray(value, keyName, targetItem)) {
                    // Keep as formatted string for now, will be converted to array in collectFormData
                    processedValue = value;
                } else {
                    // Process as regular formatted content
                    processedValue = processFormattedContentEnhanced(value, true, targetItem, keyName);
                }
            } else {
                processedValue = value;
            }

            targetData.key_values[kvIndex][field] = processedValue;
            targetData.hasUnsavedChanges = true;

            // Reset save button state
            const saveBtn = isSubdoc ?
                document.getElementById(`saveBtn_subdoc_${parentIndex}_${subdocIndex}`) :
                document.getElementById(`saveBtn_${index}`);
            if (saveBtn && saveBtn.classList.contains('saved')) {
                saveBtn.textContent = 'Save changes';
                saveBtn.classList.remove('saved');
            }
        }

        console.log(`Saved ${field} for ${isSubdoc ? 'subdoc' : 'item'} ${index}, kv ${kvIndex}:`, processedValue);
    }
}

// Subdocument functions
function toggleSubdocument(parentIndex, subdocIndex) {
    const subdocId = `subdoc_${parentIndex}_${subdocIndex}`;
    const header = document.querySelector(`#${subdocId} .subdocument-header`);
    const content = document.querySelector(`#${subdocId} .subdocument-content`);

    if (!header || !content) return;

    // If this subdocument is already expanded, close it
    if (header.classList.contains('expanded')) {
        header.classList.remove('expanded');
        content.classList.remove('show');
        expandedSubdocument = null;
    } else {
        // Close any previously expanded subdocument
        if (expandedSubdocument) {
            const prevHeader = document.querySelector(`#${expandedSubdocument} .subdocument-header`);
            const prevContent = document.querySelector(`#${expandedSubdocument} .subdocument-content`);
            if (prevHeader) prevHeader.classList.remove('expanded');
            if (prevContent) prevContent.classList.remove('show');
        }

        // Expand this subdocument
        header.classList.add('expanded');
        content.classList.add('show');
        expandedSubdocument = subdocId;
    }
}

function removeSubdocument(parentIndex, subdocIndex) {
    if (!confirm('Are you sure you want to remove this subdocument?')) {
        return;
    }
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item && item.data && item.data.subdocument) {
        item.data.subdocument.splice(subdocIndex, 1);
        item.hasUnsavedChanges = true;
        renderExtractedData();
    }
}

// Image functions
function openImageModal(base64) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    modal.style.display = "block";
    modalImg.src = base64;
}

function closeImageModal() {
    const modal = document.getElementById('imageModal');
    modal.style.display = "none";
}

// Click outside modal to close
window.onclick = function(event) {
    const modal = document.getElementById('imageModal');
    if (event.target == modal) {
        closeImageModal();
    }
}

function removeImage(parentIndex, imageIndex, isSubdoc = false, subdocIndex = null) {
    if (!confirm('Are you sure you want to remove this image?')) {
        return;
    }
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        let targetData;
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            targetData = item.data.subdocument[subdocIndex];
        } else if (!isSubdoc && item.data) {
            targetData = item.data;
        }

        if (targetData && targetData.images) {
            targetData.images.splice(imageIndex, 1);
            targetData.hasUnsavedChanges = true;
            renderExtractedData();
        }
    }
}

// Pagination functions with bottom controls update
function updatePaginationControls() {
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const totalValidItems = validItems.length;

    // Update top controls
    document.getElementById('currentItemIndex').textContent = totalValidItems > 0 ? currentPage : 0;
    document.getElementById('totalItems').textContent = totalValidItems;

    // Update bottom controls
    document.getElementById('currentItemIndexBottom').textContent = totalValidItems > 0 ? currentPage : 0;
    document.getElementById('totalItemsBottom').textContent = totalValidItems;

    // Update page numbers - only show current page
    const pageNumbersContainer = document.getElementById('pageNumbers');
    const pageNumbersContainerBottom = document.getElementById('pageNumbersBottom');

    pageNumbersContainer.innerHTML = '';
    pageNumbersContainerBottom.innerHTML = '';

    if (totalValidItems === 0) {
        // Update button states for no items
        ['firstPageBtn', 'prevPageBtn', 'nextPageBtn', 'lastPageBtn',
         'firstPageBtnBottom', 'prevPageBtnBottom', 'nextPageBtnBottom', 'lastPageBtnBottom'].forEach(id => {
            document.getElementById(id).disabled = true;
        });

        document.getElementById('pageJumpInput').max = 0;
        document.getElementById('pageJumpInput').value = 0;
        document.getElementById('pageJumpInputBottom').max = 0;
        document.getElementById('pageJumpInputBottom').value = 0;
        return;
    }

    // Only show current page number
    const pageBtn = document.createElement('button');
    pageBtn.className = 'page-btn active';
    pageBtn.textContent = currentPage;
    pageBtn.disabled = true;
    pageNumbersContainer.appendChild(pageBtn);

    const pageBtnBottom = pageBtn.cloneNode(true);
    pageNumbersContainerBottom.appendChild(pageBtnBottom);

    // Update button states
    document.getElementById('firstPageBtn').disabled = currentPage === 1;
    document.getElementById('prevPageBtn').disabled = currentPage === 1;
    document.getElementById('nextPageBtn').disabled = currentPage === totalPages;
    document.getElementById('lastPageBtn').disabled = currentPage === totalPages;

    document.getElementById('firstPageBtnBottom').disabled = currentPage === 1;
    document.getElementById('prevPageBtnBottom').disabled = currentPage === 1;
    document.getElementById('nextPageBtnBottom').disabled = currentPage === totalPages;
    document.getElementById('lastPageBtnBottom').disabled = currentPage === totalPages;

    // Update page jump inputs
    document.getElementById('pageJumpInput').max = totalPages;
    document.getElementById('pageJumpInput').value = currentPage;
    document.getElementById('pageJumpInputBottom').max = totalPages;
    document.getElementById('pageJumpInputBottom').value = currentPage;
}

function resetAllSaveButtonStates() {
    // Find all save buttons and reset their states
    document.querySelectorAll('[id^="saveBtn_"]').forEach(btn => {
        // Clear any existing timeout
        if (btn.resetTimeout) {
            clearTimeout(btn.resetTimeout);
        }

        // Reset button appearance
        btn.textContent = 'Save current changes';
        btn.classList.remove('saved');
        btn.disabled = false;
    });

    // Also reset any "hasUnsavedChanges" flags in the data
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    validItems.forEach(item => {
        if (item.hasUnsavedChanges !== undefined) {
            // Don't change the flag, just ensure buttons reflect current state
        }

        // Check subdocuments recursively
        function resetSubdocFlags(subdocs) {
            if (subdocs && Array.isArray(subdocs)) {
                subdocs.forEach(subdoc => {
                    if (subdoc.hasUnsavedChanges !== undefined) {
                        // Don't change the flag
                    }
                    if (subdoc.subdocument) {
                        resetSubdocFlags(subdoc.subdocument);
                    }
                });
            }
        }

        if (item.data && item.data.subdocument) {
            resetSubdocFlags(item.data.subdocument);
        }
    });
}

function goToPage(page) {
    if (page >= 1 && page <= totalPages && page !== currentPage) {
        // Reset all save button states before changing page
        resetAllSaveButtonStates();

        expandedSubdocument = null; // Reset expanded subdocument when changing pages
        expandedSubdocumentPaths.clear(); // Clear all expanded subdocument tracking
        currentPage = page;
        renderExtractedData();
    }
}

function goToPrevPage() {
    if (currentPage > 1) {
        goToPage(currentPage - 1);
    }
}

function goToNextPage() {
    if (currentPage < totalPages) {
        goToPage(currentPage + 1);
    }
}

function jumpToPage() {
    const pageInput = document.getElementById('pageJumpInput');
    const page = parseInt(pageInput.value);
    if (!isNaN(page)) {
        goToPage(page);
    }
}

function jumpToPageBottom() {
    const pageInput = document.getElementById('pageJumpInputBottom');
    const page = parseInt(pageInput.value);
    if (!isNaN(page)) {
        goToPage(page);
    }
}

// Helper function to render subdocument item
function renderSubdocumentItem(subdoc, parentIndex, subdocIndex) {
    const subdocId = `subdoc_${parentIndex}_${subdocIndex}`;

    // Initialize subdoc data structures if missing
    if (!subdoc.media_type) subdoc.media_type = 'text/plain';
    if (!subdoc.description) subdoc.description = subdoc.summary || '';
    if (!subdoc.manual_tags) subdoc.manual_tags = [];
    if (!subdoc.auto_tags) {
        // Process tags from subdoc.tags if available
        if (subdoc.tags && Array.isArray(subdoc.tags)) {
            subdoc.auto_tags = subdoc.tags.map(tag => {
                if (typeof tag === 'object' && tag.text) {
                    return tag.text;
                } else if (typeof tag === 'string') {
                    return tag;
                }
                return '';
            }).filter(tag => tag);
        } else {
            subdoc.auto_tags = [];
        }
    }
    if (!subdoc.key_values) subdoc.key_values = [];

    // Check if subdocument was manually saved
    const saveButtonText = (subdoc.manuallySaved && !subdoc.hasUnsavedChanges) ? '✓ Saved' : 'Save changes';
    const saveButtonClass = (subdoc.manuallySaved && !subdoc.hasUnsavedChanges) ? 'btn btn-save saved' : 'btn btn-save';

    // Generate tags HTML
    const manualTagsHtml = subdoc.manual_tags.map(tag => {
        let tagText = typeof tag === 'object' && tag.text ? tag.text : tag;
        const escapedTagText = tagText.replace(/'/g, "\\'").replace(/"/g, '&quot;');

        return `
            <span class="tag manual">
                ${tagText}
                <span class="remove-tag" onclick="removeTag(${parentIndex}, '${escapedTagText}', 'manual', true, ${subdocIndex})">×</span>
            </span>
        `;
    }).join('');

    const autoTagsHtml = subdoc.auto_tags.map(tag => {
        // Extract tag text properly
        let tagText = '';
        if (typeof tag === 'object' && tag.text) {
            tagText = tag.text;
        } else if (typeof tag === 'string') {
            tagText = tag;
        }

        // Escape single quotes in tag text for onclick handler
        const escapedTagText = tagText.replace(/'/g, "\\'").replace(/"/g, '&quot;');


        return `
            <span class="tag auto">
                ${tagText}
                <span class="remove-tag" onclick="removeTag(${parentIndex}, '${escapedTagText}', 'auto', true, ${subdocIndex})">×</span>
            </span>
        `;
    }).join('');

    // Generate key-values HTML
    const kvHtml = subdoc.key_values.map((kv, kvIndex) => `
        <div class="key-value-pair">
            <input type="text" value="${kv.key || ''}" id="key_subdoc_${parentIndex}_${subdocIndex}_${kvIndex}"
                   onchange="saveKeyValueData(${parentIndex}, ${kvIndex}, 'key', this.value, true, ${parentIndex}, ${subdocIndex})">
            <input type="text" value="${kv.value || ''}" id="value_subdoc_${parentIndex}_${subdocIndex}_${kvIndex}"
                   onchange="saveKeyValueData(${parentIndex}, ${kvIndex}, 'value', this.value, true, ${parentIndex}, ${subdocIndex})">
            <button class="remove-kv-btn" onclick="removeKeyValue(${parentIndex}, ${kvIndex}, true, ${subdocIndex})">Remove</button>
        </div>
    `).join('');

    // Generate images HTML
    let imagesHtml = '';
    if (subdoc.images && subdoc.images.length > 0) {
        const imagesGridHtml = subdoc.images.map((img, imgIndex) => `
            <div class="image-item">
                <img src="${img.base64}" alt="Image ${imgIndex + 1}" class="image-preview"
                    onclick="event.stopPropagation(); openImageModal('${img.base64}')">
                <div class="image-info">
                    ${img.page ? `<div class="image-page">Page ${img.page}</div>` : ''}
                    ${img.width && img.height ? `<div>${img.width}x${img.height}</div>` : ''}
                </div>
                <button class="remove-image-btn" onclick="removeImage(${parentIndex}, ${imgIndex}, true, ${subdocIndex})">Remove</button>
            </div>
        `).join('');

        imagesHtml = `
            <div class="images-section">
                <div class="images-header">Images (${subdoc.images.length})</div>
                <div class="images-grid">
                    ${imagesGridHtml}
                </div>
            </div>
        `;
    }

    // Check if subdocument is an Excel file by extension or media type
    const legacyExcelMediaTypes = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'application/vnd.google-apps.spreadsheet'
    ];
    const isLegacySubdocExcelByType = subdoc.media_type && legacyExcelMediaTypes.includes(subdoc.media_type);
    const isLegacySubdocExcelByUrl = (subdoc.file_url && (subdoc.file_url.toLowerCase().endsWith('.xlsx') || subdoc.file_url.toLowerCase().endsWith('.xls'))) ||
                                     (subdoc.url && subdoc.url.length > 0 && (subdoc.url[0].toLowerCase().endsWith('.xlsx') || subdoc.url[0].toLowerCase().endsWith('.xls')));
    const isLegacySubdocExcel = isLegacySubdocExcelByType || isLegacySubdocExcelByUrl;

    const legacySubdocMarkdownHtml = isLegacySubdocExcel ? `
                <div class="field-group">
                    <label>Markdown Content</label>
                    <textarea id="extracted_text_subdoc_${parentIndex}_${subdocIndex}"
                              onchange="saveFieldData(${parentIndex}, 'extracted_text', this.value, true, ${parentIndex}, ${subdocIndex})" style="min-height: 150px;">${subdoc.extracted_text || ''}</textarea>
                </div>
    ` : '';

    return `
        <div class="subdocument-item" id="${subdocId}">
            <div class="subdocument-header" onclick="toggleSubdocument(${parentIndex}, ${subdocIndex})">
                <div class="subdocument-title">
                    ${subdoc.title || `Subdocument ${subdocIndex + 1}`}
                </div>
                <div class="subdocument-controls">
                    <button class="remove-subdoc-btn" onclick="event.stopPropagation(); removeSubdocument(${parentIndex}, ${subdocIndex})">Remove</button>
                    <svg class="expand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </div>
            </div>
            <div class="subdocument-content">
                <div class="field-group">
                    <label>Resource Type</label>
                    <select id="mediaType_subdoc_${parentIndex}_${subdocIndex}" onchange="saveFieldData(${parentIndex}, 'media_type', this.value, true, ${parentIndex}, ${subdocIndex})">
                        {% for value, label in media_types %}
                        <option value="{{ value }}" ${subdoc.media_type === '{{ value }}' ? 'selected' : ''}>{{ label }}</option>
                        {% endfor %}
                    </select>
                </div>

                <div class="field-group">
                    <label>Summary</label>
                    <textarea id="description_subdoc_${parentIndex}_${subdocIndex}"
                              onchange="saveFieldData(${parentIndex}, 'description', this.value, true, ${parentIndex}, ${subdocIndex})">${subdoc.description || ''}</textarea>
                </div>

                ${legacySubdocMarkdownHtml}

                <div class="field-group">
                    <label>Sections</label>
                    <div class="key-values" id="kvContainer_subdoc_${parentIndex}_${subdocIndex}">
                        ${kvHtml}
                    </div>
                    <button class="add-kv-btn" onclick="addKeyValue(${parentIndex}, true, ${subdocIndex})">Add Field</button>
                </div>

                ${imagesHtml}

                <div style="margin-top: 20px; text-align: right;">
                    <button class="${saveButtonClass}" id="saveBtn_subdoc_${parentIndex}_${subdocIndex}"
                            onclick="saveCurrentFile(${parentIndex}, true, ${parentIndex}, ${subdocIndex})">${saveButtonText}</button>
                </div>
            </div>
        </div>
    `;
}

function processFormattedContent(value, isKeyValue = false) {
    if (!value || typeof value !== 'string') {
        return value;
    }

    // Check if content has bullet points or numbered lists
    const hasBullets = value.includes('•') || /^\s*[-*]\s+/m.test(value) || /^\s*\d+\.\s+/m.test(value);
    const hasNewlines = value.includes('\n');

    if (hasBullets && hasNewlines) {
        // Split into lines and process
        const lines = value.split('\n').map(line => line.trim()).filter(line => line.length > 0);
        const processedLines = lines.map(line => {
            // Remove bullet points and numbering
            return line.replace(/^[•\-*]\s*/, '').replace(/^\d+\.\s*/, '').trim();
        }).filter(line => line.length > 0);

        if (isKeyValue && processedLines.length > 1) {
            // For key-values with multiple items, format as bullet list
            return processedLines.map(line => `• ${line}`).join('\n');
        } else if (processedLines.length > 1) {
            // For other content, preserve as formatted list
            return processedLines.map(line => `• ${line}`).join('\n');
        }
    }

    return value;
}

function autoResizeTextarea(textarea) {
    if (!textarea) return;

    textarea.style.height = 'auto';

    // Get the key name for this textarea
    const keyInput = textarea.closest('.key-value-pair')?.querySelector('.kv-key-input');
    const keyName = keyInput ? keyInput.value : '';

    // Check if content should be formatted as a list
    const value = textarea.value;

    // Try to get the item context for better array detection
    let itemContext = null;
    const mediaItem = textarea.closest('.media-item');
    if (mediaItem) {
        const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
        const actualIndex = (currentPage - 1) * itemsPerPage;
        itemContext = validItems[actualIndex];
    }

    const shouldBeArray = shouldPreserveAsArray(value, keyName, itemContext);
    const shouldBeFormatted = shouldBeArray || isFormattedListContent(value);

    if (shouldBeFormatted && !textarea.classList.contains('formatted-list')) {
        textarea.classList.add('formatted-list');
        if (value.length > 200) {
            textarea.classList.add('long-content');
        }
    } else if (!shouldBeFormatted && textarea.classList.contains('formatted-list')) {
        textarea.classList.remove('formatted-list', 'long-content');
    }

    // For formatted list content, ensure minimum height
    if (textarea.classList.contains('formatted-list')) {
        const minHeight = textarea.classList.contains('long-content') ? 120 : 80;
        const scrollHeight = Math.max(textarea.scrollHeight, minHeight);
        textarea.style.height = scrollHeight + 'px';
    } else {
        textarea.style.height = (textarea.scrollHeight) + 'px';
    }
}

function resizeAllTextareas() {
    document.querySelectorAll('.key-value-textarea').forEach(textarea => {
        autoResizeTextarea(textarea);
    });
}

function addTagFromDropdown(itemIndex, tagValue, isSubdoc = false, subdocIndex = null) {
    if (!tagValue) return;

    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        let targetData;
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            targetData = item.data.subdocument[subdocIndex];
        } else if (!isSubdoc && item.data) {
            targetData = item.data;
        }

        if (targetData) {
            if (!targetData.manual_tags) {
                targetData.manual_tags = [];
            }

            // Check if tag already exists
            if (!targetData.manual_tags.includes(tagValue)) {
                targetData.manual_tags.push(tagValue);
                targetData.hasUnsavedChanges = true;

                // Reset save button state
                const saveBtn = isSubdoc ?
                    document.getElementById(`saveBtn_subdoc_${itemIndex}_${subdocIndex}`) :
                    document.getElementById(`saveBtn_${itemIndex}`);
                if (saveBtn && saveBtn.classList.contains('saved')) {
                    saveBtn.textContent = 'Save current changes';
                    saveBtn.classList.remove('saved');
                }

                renderExtractedData();
            }

            // Reset dropdown
            const dropdown = document.getElementById(
                isSubdoc ?
                `tagDropdown_subdoc_${itemIndex}_${subdocIndex}` :
                `tagDropdown_${itemIndex}`
            );
            if (dropdown) {
                dropdown.value = '';
            }
        }
    }
}

// Helper functions for structured content handling

function isArrayField(key, item) {
    // Check if this field was originally an array by looking at metadata
    if (item.data && item.data.array_fields_metadata) {
        return item.data.array_fields_metadata.includes(key);
    }

    // Fallback: check key-value metadata
    if (item.data && item.data.key_values) {
        const kv = item.data.key_values.find(kvPair => kvPair.key === key);
        return kv && kv.original_type === 'array';
    }

    return false;
}

function convertBulletPointsToArray(text) {
    /**
     * Convert bullet-pointed text back to array
     * Handles various bullet point formats: •, -, *, numbered lists
     */
    if (!text || typeof text !== 'string') {
        return [];
    }

    const lines = text.split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);

    const items = [];

    for (const line of lines) {
        // Remove bullet points and numbering
        let cleanLine = line
            .replace(/^[•\-*]\s*/, '')           // Remove •, -, * bullets
            .replace(/^\d+\.\s*/, '')           // Remove numbered lists (1., 2., etc.)
            .replace(/^\([a-zA-Z0-9]+\)\s*/, '') // Remove lettered lists (a), (1), etc.
            .trim();

        if (cleanLine.length > 0) {
            items.push(cleanLine);
        }
    }

    return items;
}

function convertArrayToBulletPoints(array) {
    /**
     * Convert array to bullet-pointed text for display
     */
    if (!Array.isArray(array)) {
        return array;
    }

    return array
        .filter(item => item !== null && item !== undefined)
        .map(item => `• ${String(item).trim()}`)
        .join('\n');
}

function shouldPreserveAsArray(value, key, item) {
    /**
     * Determine if a field should be saved as an array based on:
     * 1. Original type metadata
     * 2. Content analysis (has bullet points)
     * 3. Field name patterns
     */

    // Check metadata first
    if (isArrayField(key, item)) {
        return true;
    }

    // Check if content looks like a list
    if (typeof value === 'string' && value.trim()) {
        const lines = value.split('\n').filter(line => line.trim().length > 0);

        // Multiple lines with bullet points
        if (lines.length > 1) {
            const bulletLines = lines.filter(line =>
                /^[•\-*]\s+/.test(line.trim()) || /^\d+\.\s+/.test(line.trim())
            );

            // If majority of lines have bullets, treat as array
            if (bulletLines.length / lines.length >= 0.7) {
                return true;
            }
        }
    }

    // Common field names that are typically arrays
    const arrayFieldPatterns = [
        /COMPONENTS?$/i,
        /STEPS?$/i,
        /ITEMS?$/i,
        /LIST$/i,
        /ELEMENTS?$/i,
        /FACTORS?$/i,
        /RISKS?$/i,
        /LEARNINGS?$/i,
        /CONTRIBUTORS?$/i,
        /ASSETS?$/i,
        /PREFERENCES?$/i,
        /EVIDENCE$/i,
        /THEORY.*CHANGE$/i,
        /IMPLEMENTATION.*MODEL$/i
    ];

    return arrayFieldPatterns.some(pattern => pattern.test(key));
}

function processStructuredContentForSave(keyValues, item) {
    /**
     * Process key-values for saving, converting between arrays and strings as needed
     */
    return keyValues.map(kv => {
        const key = kv.key;
        const value = kv.value;

        if (shouldPreserveAsArray(value, key, item)) {
            // Convert bullet points back to array
            if (typeof value === 'string') {
                const arrayValue = convertBulletPointsToArray(value);
                return {
                    key: key,
                    value: arrayValue,
                    original_type: 'array'
                };
            }
        } else {
            // Keep as string, but clean up formatting
            let cleanValue = value;
            if (typeof value === 'string') {
                // Preserve intentional paragraph breaks
                cleanValue = value
                    .split('\n')
                    .map(line => line.trim())
                    .join('\n')
                    .replace(/\n{3,}/g, '\n\n'); // Limit to double line breaks
            }

            return {
                key: key,
                value: cleanValue,
                original_type: 'string'
            };
        }

        return kv;
    });
}

// Enhanced version of existing processFormattedContent function
function processFormattedContentEnhanced(value, isKeyValue = false, item = null, key = null) {
    if (!value || typeof value !== 'string') {
        return value;
    }

    // If this should be preserved as an array, don't format as bullet points
    if (item && key && shouldPreserveAsArray(value, key, item)) {
        return value; // Keep as-is for array processing later
    }

    // Check if content has bullet points or numbered lists
    const hasBullets = value.includes('•') || /^\s*[-*]\s+/m.test(value) || /^\s*\d+\.\s+/m.test(value);
    const hasNewlines = value.includes('\n');

    if (hasBullets && hasNewlines) {
        // Split into lines and process
        const lines = value.split('\n').map(line => line.trim()).filter(line => line.length > 0);
        const processedLines = lines.map(line => {
            // Remove bullet points and numbering
            return line.replace(/^[•\-*]\s*/, '').replace(/^\d+\.\s*/, '').trim();
        }).filter(line => line.length > 0);

        if (isKeyValue && processedLines.length > 1) {
            // For key-values with multiple items, format as bullet list
            return processedLines.map(line => `• ${line}`).join('\n');
        } else if (processedLines.length > 1) {
            // For other content, preserve as formatted list
            return processedLines.map(line => `• ${line}`).join('\n');
        }
    }

    return value;
}

// ============================================
// SECTION 4: STEP 2 - REVIEW FUNCTIONS
// ============================================
// Data rendering
function renderExtractedData() {
    const container = document.getElementById('extractedDataContainer');
    container.innerHTML = '';

    // Only show successful uploads
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    totalPages = Math.ceil(validItems.length / itemsPerPage);

    if (validItems.length === 0) {
        updatePaginationControls();
        return;
    }

    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, validItems.length);

    for (let pageIndex = startIndex; pageIndex < endIndex; pageIndex++) {
        const item = validItems[pageIndex];
        const displayIndex = pageIndex;
        const mediaItem = document.createElement('div');
        mediaItem.className = 'media-item active';

        // Check if this item was manually saved and has no unsaved changes
        const isSaved = item.manuallySaved && !item.hasUnsavedChanges;
        const saveButtonText = isSaved ? '✓ Saved' : 'Save current changes';
        const saveButtonClass = isSaved ? 'btn btn-save saved' : 'btn btn-save';

        // Auto-tags content
        const autoTagsContent = (item.data.auto_tags || []).map(tag => {
            const escapedTag = tag.replace(/'/g, "\\'").replace(/"/g, '&quot;');
            return `
                <span class="tag auto">
                    ${tag}
                    <span class="remove-tag" onclick="removeTag(${displayIndex}, '${escapedTag}', 'auto')">×</span>
                </span>
            `;
        }).join('');

        // Subdocuments content with informational message
        let subdocsHtml = '';
        if (item.data.subdocument && item.data.subdocument.length > 0) {
            subdocsHtml = `
                <div class="subdocuments-section">
                    <div class="subdocuments-header">
                        Subdocuments
                        <span class="subdocument-count">(${item.data.subdocument.length})</span>
                    </div>
                    <div class="subdocument-info-message">
                        <div style="background-color: #e3f2fd; border: 1px solid #90caf9; border-radius: 6px; padding: 15px; margin: 15px 0; color: #1565c0;">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1565c0" stroke-width="2" style="vertical-align: middle; margin-right: 8px;">
                                <circle cx="12" cy="12" r="10"></circle>
                                <line x1="12" y1="16" x2="12" y2="12"></line>
                                <line x1="12" y1="8" x2="12.01" y2="8"></line>
                            </svg>
                            <strong>Information:</strong> These linked files will also be uploaded. Please review them for correctness of metadata.
                        </div>
                    </div>
                    ${renderNestedSubdocuments(item.data.subdocument, String(displayIndex), displayIndex)}
                </div>
            `;
        }

        // Images content
        let imagesHtml = '';
        if (item.data.images && item.data.images.length > 0) {
            const imagesGridHtml = item.data.images.map((img, imgIndex) => `
                <div class="image-item">
                    <img src="${img.base64}" alt="Image ${imgIndex + 1}" class="image-preview"
                         onclick="openImageModal('${img.base64}')">
                    <div class="image-info">
                        ${img.page ? `<div class="image-page">Page ${img.page}</div>` : ''}
                        ${img.width && img.height ? `<div>${img.width}x${img.height}</div>` : ''}
                    </div>
                    <button class="remove-image-btn" onclick="removeImage(${displayIndex}, ${imgIndex})">Remove</button>
                </div>
            `).join('');

            imagesHtml = `
                <div class="images-section">
                    <div class="images-header">Images (${item.data.images.length})</div>
                    <div class="images-grid">
                        ${imagesGridHtml}
                    </div>
                </div>
            `;
        }

        // Generate key-values HTML with document type dropdown support for main document
        const keyValuesHtml = updateMainDocumentKeyValueHtml(item, displayIndex);

        // Check if file is Excel to show Markdown Content field
        const isExcelFile = item.filename && (item.filename.toLowerCase().endsWith('.xlsx') || item.filename.toLowerCase().endsWith('.xls'));
        const markdownContentHtml = isExcelFile ? `
            <div class="field-group">
                <label>Markdown Content</label>
                <textarea class="editable-field" id="extracted_text_${displayIndex}"
                    onchange="saveFieldData(${displayIndex}, 'extracted_text', this.value)"
                    style="min-height: 150px;"
                >
                    ${item.data.extracted_text || item.data.exact_content || ''}
                </textarea>
            </div>
        ` : '';

        mediaItem.innerHTML = `
            <div class="media-item-header">
                <div class="media-item-title">
                    ${item.filename}
                    ${item.manuallySaved ? '<span style="color: #5cb85c; font-size: 14px; margin-left: 10px;">(Saved at ' + new Date(item.savedAt).toLocaleTimeString() + ')</span>' : ''}
                </div>
                <div class="media-item-actions">
                    <button class="${saveButtonClass}" id="saveBtn_${displayIndex}" onclick="saveCurrentFile(${displayIndex})">${saveButtonText}</button>
                    <button class="btn btn-secondary" onclick="removeExtractedItem(${pageIndex})">Remove</button>
                </div>
            </div>

            <div class="field-group">
                <label>Resource Type</label>
                <select id="mediaType_${displayIndex}" onchange="saveFieldData(${displayIndex}, 'media_type', this.value)">
                    {% for value, label in media_types %}
                    <option value="{{ value }}" ${item.data.media_type === '{{ value }}' ? 'selected' : ''}>{{ label }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="field-group">
                <label>Summary</label>
                <textarea class="editable-field" id="description_${displayIndex}" onchange="saveFieldData(${displayIndex}, 'description', this.value)">${item.data.description || ''}</textarea>
            </div>

            ${markdownContentHtml}

            <div class="field-group">
                <label>Tags</label>
                <div class="tags-section">
                    <div class="tags-subsection">
                        <h4>Manual Tags</h4>
                        <div class="tags-input" id="manualTagsContainer_${displayIndex}">
                            ${(item.data.manual_tags || []).map(tag => {
                                const escapedTag = tag.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                                return `
                                    <span class="tag manual">
                                        ${tag}
                                        <span class="remove-tag" onclick="removeTag(${displayIndex}, '${escapedTag}', 'manual')">×</span>
                                    </span>
                                `;
                            }).join('')}

                            <div class="tag-input-wrapper">
                                <div class="custom-dropdown" id="customTagDropdown_${displayIndex}">
                                    <input type="text"
                                           class="dropdown-search"
                                           placeholder="Search or add tag..."
                                           onclick="toggleTagDropdown('${displayIndex}')"
                                           oninput="filterTagDropdown('${displayIndex}', this.value)"
                                           onkeypress="handleTagDropdownKeypress(event, '${displayIndex}')">
                                    <div class="dropdown-list" id="tagDropdownList_${displayIndex}">
                                        ${existingManualTags.map(tag => `
                                            <div class="dropdown-option" onclick="selectTagFromDropdown('${displayIndex}', '${tag.replace(/'/g, "\\'")}')">
                                                ${tag}
                                            </div>
                                        `).join('')}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="tags-subsection">
                        <h4>Auto Tags</h4>
                        <div class="tags-input" id="autoTagsContainer_${displayIndex}">
                            ${autoTagsContent}
                        </div>
                    </div>
                </div>
            </div>

            <div class="field-group">
                <label>Sections</label>
                <div class="key-values" id="kvContainer_${displayIndex}">
                    ${keyValuesHtml}
                </div>
                <button class="add-kv-btn" onclick="addKeyValue(${displayIndex})">Add Field</button>
            </div>

            ${subdocsHtml}
            ${imagesHtml}
        `;
        container.appendChild(mediaItem);
    }

    updatePaginationControls();

    // Reset all save button timeouts after rendering
    setTimeout(() => {
        resizeAllTextareas();
        restoreExpandedStates();
        resetAllSaveButtonStates();
    }, 100);
}

function removeExtractedItem(validIndex) {
    if (!confirm('Are you sure you want to remove this file? This will remove it completely from the review.')) {
        return;
    }
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const itemToRemove = validItems[validIndex];

    if (itemToRemove) {
        // Find and remove from extractedData
        const actualIndex = extractedData.findIndex(item => item.id === itemToRemove.id);
        if (actualIndex >= 0) {
            extractedData.splice(actualIndex, 1);
        }

        // Find and remove from uploadedFiles
        const fileIndex = uploadedFiles.findIndex(f => f.name === itemToRemove.filename);
        if (fileIndex >= 0) {
            uploadedFiles.splice(fileIndex, 1);
        }
    }

    // Recalculate pagination
    const remainingValidItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    totalPages = Math.ceil(remainingValidItems.length / itemsPerPage);

    if (currentPage > totalPages && totalPages > 0) {
        currentPage = totalPages;
    }

    renderExtractedData();

    if (remainingValidItems.length === 0) {
        updateStepIndicator(1);
        updateFileList();
    }
}

function removeTag(itemIndex, tag, tagType, isSubdoc = false, subdocIndex = null) {
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        let targetData;
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            targetData = item.data.subdocument[subdocIndex];
        } else if (!isSubdoc && item.data) {
            targetData = item.data;
        }

        if (targetData) {
            const tagArray = tagType === 'manual' ? 'manual_tags' : 'auto_tags';
            if (targetData[tagArray]) {
                const tagIndex = targetData[tagArray].indexOf(tag);
                if (tagIndex > -1) {
                    targetData[tagArray].splice(tagIndex, 1);
                    targetData.hasUnsavedChanges = true;
                    renderExtractedData();
                }
            }
        }
    }
}

function handleTagInput(event, itemIndex, tagType, isSubdoc = false, subdocIndex = null) {
    if (event.key === 'Enter') {
        event.preventDefault();
        const input = event.target;
        const tag = input.value.trim();

        const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
        const actualIndex = (currentPage - 1) * itemsPerPage;
        const item = validItems[actualIndex];

        if (item && tag) {
            let targetData;
            if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
                targetData = item.data.subdocument[subdocIndex];
            } else if (!isSubdoc && item.data) {
                targetData = item.data;
            }

            if (targetData) {
                const tagArray = tagType === 'manual' ? 'manual_tags' : 'auto_tags';
                if (!targetData[tagArray]) {
                    targetData[tagArray] = [];
                }

                if (!targetData[tagArray].includes(tag)) {
                    targetData[tagArray].push(tag);
                    targetData.hasUnsavedChanges = true;
                    renderExtractedData();
                }
            }
        }
    }
}

function removeKeyValue(itemIndex, kvIndex, isSubdoc = false, subdocIndex = null) {
    if (!confirm('Are you sure you want to remove this section?')) {
        return;
    }
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        let targetData;
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            targetData = item.data.subdocument[subdocIndex];
        } else if (!isSubdoc && item.data) {
            targetData = item.data;
        }

        if (targetData && targetData.key_values) {
            targetData.key_values.splice(kvIndex, 1);
            targetData.hasUnsavedChanges = true;
            renderExtractedData();
        }
    }
}

function addKeyValue(itemIndex, isSubdoc = false, subdocIndex = null) {
    const validItems = extractedData.filter(item => item.status === FILE_STATUS.SUCCESS);
    const actualIndex = (currentPage - 1) * itemsPerPage;
    const item = validItems[actualIndex];

    if (item) {
        let targetData;
        if (isSubdoc && item.data.subdocument && item.data.subdocument[subdocIndex]) {
            targetData = item.data.subdocument[subdocIndex];
        } else if (!isSubdoc && item.data) {
            targetData = item.data;
        }

        if (targetData) {
            if (!targetData.key_values) {
                targetData.key_values = [];
            }
            targetData.key_values.push({
                key: '',
                value: '',
                source: 'user', // Mark as user-added
                original_type: 'string'
            });
            targetData.hasUnsavedChanges = true;
            renderExtractedData();
        }
    }
}

// Collect form data before saving
function collectFormData() {
    extractedData.forEach((item) => {
        if (item && item.status === FILE_STATUS.SUCCESS && item.data) {
            // Get the selected organization for saving to Media model FK
            const selectedOrgSlug = selectedOrganization ? selectedOrganization.slug : null;
            const selectedOrgName = selectedOrganization ? selectedOrganization.name : (userCompanyName || '');

            // Store organization info for Media model FK
            item.data.organization_slug = selectedOrgSlug;
            item.data.organization = selectedOrgName;

            // Remove ORGANIZATION from key_values as it will be saved to Media FK
            if (item.data.key_values) {
                item.data.key_values = item.data.key_values.filter(kv => kv.key !== 'ORGANIZATION');
                item.data.key_values = processStructuredContentForSave(item.data.key_values, item);
            }

            // Combine manual and auto tags for saving
            if (item.data.auto_tags_full) {
                item.data.auto_tags = item.data.auto_tags_full;
            }
            item.data.tags = [...(item.data.manual_tags || []), ...(item.data.auto_tags || [])];

            // Process subdocuments recursively
            function processSubdocs(subdocs, parentOrgSlug, parentOrgName) {
                if (subdocs && Array.isArray(subdocs)) {
                    subdocs.forEach(subdoc => {
                        // Set organization info for subdocument
                        subdoc.organization_slug = parentOrgSlug;
                        subdoc.organization = parentOrgName;

                        // Process subdocument key-values and remove ORGANIZATION
                        if (subdoc.key_values) {
                            subdoc.key_values = subdoc.key_values.filter(kv => kv.key !== 'ORGANIZATION');
                            subdoc.key_values = processStructuredContentForSave(subdoc.key_values, { data: subdoc });
                        }

                        // Combine tags for subdocuments
                        subdoc.tags = [...(subdoc.manual_tags || []), ...(subdoc.auto_tags || [])];

                        // Process nested subdocuments
                        if (subdoc.subdocument) {
                            processSubdocs(subdoc.subdocument, parentOrgSlug, parentOrgName);
                        }
                    });
                }
            }

            processSubdocs(item.data.subdocument, selectedOrgSlug, selectedOrgName);
        }
    });
}

async function trackVectorDbBatchProgress(vectorDbTasks, totalFiles) {
    return new Promise((resolve) => {
        let completedTasks = 0;
        const taskStatuses = {};

        const checkProgress = async () => {
            // Use existing endpoint to check multiple tasks
            for (const task of vectorDbTasks) {
                if (taskStatuses[task.task_id] === 'completed') continue;

                try {
                    const response = await fetch("{% url 'admin:chatbot_media_vector_db_task_status' %}", {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrftoken,
                        },
                        body: JSON.stringify({ task_id: task.task_id })
                    });

                    const result = await response.json();
                    if (result.success && result.ready) {
                        if (taskStatuses[task.task_id] !== 'completed') {
                            taskStatuses[task.task_id] = 'completed';
                            completedTasks++;
                        }
                    }
                } catch (error) {
                    console.error(`Error checking task ${task.task_id}:`, error);
                }
            }

            // Calculate progress
            const dbSavedFiles = totalFiles - vectorDbTasks.length; // Files without vector DB tasks
            const vectorDbProgress = completedTasks;
            const totalProgress = dbSavedFiles + vectorDbProgress;
            const percentage = Math.round((totalProgress / totalFiles) * 100);

            // Show enhanced progress using existing data
            const currentFile = vectorDbTasks[completedTasks]?.filename || 'Processing...';
            showLoading(`Saving files... ${totalProgress}/${totalFiles} (${percentage}%)
                <br><small>Database: ✓ Complete</small>
                <br><small>Vector DB: ${vectorDbProgress}/${vectorDbTasks.length} complete</small>
                <br><small>Current: ${currentFile}</small>`);

            // Check if all done
            if (completedTasks >= vectorDbTasks.length) {
                showLoading(`All files saved successfully! ${totalFiles}/${totalFiles} complete`);
                setTimeout(resolve, 1000); // Brief delay to show completion
                return;
            }

            // Continue polling
            setTimeout(checkProgress, 2000); // Every 2 seconds
        };

        // Start tracking
        checkProgress();

        // Safety timeout
        setTimeout(resolve, 600000); // 10 minutes max
    });
}

// ============================================
// SECTION 5: STEP 3 - SAVE FUNCTIONS
// ============================================
// Database operations
async function saveToDatabase(data) {
    const companyBotId = document.getElementById('companyBotSelect').value;
    // Only save successful items
    const validItems = data.filter(item => item.status === FILE_STATUS.SUCCESS);
    const totalItems = validItems.length;

    const items = validItems.map(item => ({
        ...item.data,
        filename: item.filename,
        file_index: item.file_index,
        manual_tags: item.data.manual_tags || [],
        auto_tags: item.data.auto_tags || [],
        file_key: item.data.file_key,
        session_id: item.data.session_id || sessionId,
        subdocument: item.data.subdocument || [],
        source_documents: item.data.source_documents || [],
        images: item.data.images || []
    }));

    showLoading(`Saving ${totalItems} files to database...`);

    const response = await fetch("{% url 'admin:chatbot_media_batch_save' %}", {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify({
            company_bot_id: companyBotId,
            items: items,
            session_id: sessionId
        })
    });

    const result = await response.json();
    if (result.success) {

        const vectorDbTasks = result.results.filter(r => r.success && r.vector_task_id).map(r => ({
            task_id: r.vector_task_id,
            filename: r.filename
        }));

        // If there are vector DB tasks, show enhanced progress
        if (vectorDbTasks.length > 0) {
            await trackVectorDbBatchProgress(vectorDbTasks, totalItems);
        }

        return result.results.map((res, index) => {
            // If save failed, ensure file_key is preserved
            if (!res.success && items[index]) {
                res.file_key = res.file_key || items[index].file_key;
                res.session_id = res.session_id || items[index].session_id;
            }
            return {
                ...res,
                originalData: items[index]
            };
        });

    } else {
        throw new Error(result.error || 'Failed to save data');
    }
}

// Retry save for individual item
async function retrySave(resultIndex) {
    const result = saveResults[resultIndex];
    showLoading(`Retrying save for ${result.filename}...`);

    try {
        let itemData;

        // First try to use originalData if available
        if (result.originalData) {
            itemData = result.originalData;
        } else {
            // Fallback: Find the original item data
            const originalItem = extractedData.find(item =>
                item.filename === result.filename && item.status === FILE_STATUS.SUCCESS
            );

            if (!originalItem) {
                throw new Error('Original item data not found');
            }

            itemData = {
                ...originalItem.data,
                filename: originalItem.filename,
                file_index: originalItem.file_index,
                manual_tags: originalItem.data.manual_tags || [],
                auto_tags: originalItem.data.auto_tags || [],
                file_key: originalItem.data.file_key,
                session_id: originalItem.data.session_id || sessionId,
                subdocument: originalItem.data.subdocument || [],
                source_documents: originalItem.data.source_documents || [],
                images: originalItem.data.images || []
            };
        }

        if (!result.partial_success) {
            // Main document failed, so don't process subdocuments
            itemData.subdocument = [];
        }

        console.log('Retrying with data:', itemData); // Debug log

        const response = await fetch("{% url 'admin:chatbot_media_retry_save' %}", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify({
                item_data: itemData,
                company_bot_id: document.getElementById('companyBotSelect').value,
                session_id: sessionId
            })
        });

        const retryResult = await response.json();
        if (retryResult.success) {
            // Update the result
            saveResults[resultIndex] = {
                ...retryResult.result,
                originalData: itemData  // Preserve for potential future retries
            };
            displayResults(saveResults);
            showStatus(`Successfully retried save for ${result.filename}`, 'success');
        } else {
            showStatus(`Retry failed for ${result.filename}: ${retryResult.error}`, 'error');
        }
    } catch (error) {
        showStatus(`Retry failed for ${result.filename}: ${error.message}`, 'error');
    } finally {
        hideLoading();
    }
}

async function saveAnywayResult(resultIndex) {
    const result = saveResults[resultIndex];
    showLoading(`Saving ${result.filename} (bypassing similarity)...`);

    try {
        const itemData = result.originalData || {
            ...result,
            bypass_similarity: true
        };
        itemData.bypass_similarity = true;

        const response = await fetch("{% url 'admin:chatbot_media_retry_save' %}", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify({
                item_data: itemData,
                company_bot_id: document.getElementById('companyBotSelect').value,
                session_id: sessionId,
                bypass_similarity: true
            })
        });

        const retryResult = await response.json();
        if (retryResult.success) {
            saveResults[resultIndex] = {
                ...retryResult.result,
                originalData: itemData
            };
            displayResults(saveResults);
            showStatus(`Successfully saved ${result.filename} (similarity check bypassed)`, 'success');
        } else {
            showStatus(`Save failed for ${result.filename}: ${retryResult.error}`, 'error');
        }
    } catch (error) {
        showStatus(`Save failed for ${result.filename}: ${error.message}`, 'error');
    } finally {
        hideLoading();
    }
}

// Global variable to store save results for retry functionality
let saveResults = [];

// Save button handler
document.getElementById('saveBtn').addEventListener('click', async () => {
    collectFormData();
    showLoading('Saving to database...');

    try {
        const results = await saveToDatabase(extractedData);
        saveResults = results;
        displayResults(results);
        updateStepIndicator(3);
    } catch (error) {
        showStatus('Error saving data: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
});

function renderSubdocumentResults(subdocResults, parentIndex, depth = 0) {
    let html = '<div class="subdoc-hierarchy">';

    subdocResults.forEach((subdoc, subdocIndex) => {
        const retryButton = !subdoc.success ?
            `<button class="btn retry-btn" onclick="retrySubdocSave(${parentIndex}, '${subdoc.path}', '${subdoc.cache_key}')">Retry</button>` : '';

        html += `
            <div class="subdoc-result-item ${subdoc.success ? 'success' : 'error'}">
                <div style="flex: 1;">
                    <strong>${subdoc.title}</strong>
                    ${subdoc.success ?
                        `<span style="color: #5cb85c; margin-left: 10px;">✓ Saved</span>` :
                        `<span style="color: #f44336; margin-left: 10px;">✗ ${subdoc.error || 'Failed'}</span>`
                    }
                </div>
                ${retryButton}
            </div>
        `;

        // Render nested subdocuments recursively
        if (subdoc.nested_subdocument_results && subdoc.nested_subdocument_results.length > 0) {
            html += renderSubdocumentResults(subdoc.nested_subdocument_results, parentIndex, depth + 1);
        }
    });

    html += '</div>';
    return html;
}

async function retrySubdocSave(parentIndex, path, cacheKey) {
    const result = saveResults[parentIndex];

    // Get subdocument data from cache
    const cachedData = await getCachedSubdocument(cacheKey);
    if (!cachedData || !cachedData.data) {
        showStatus('Subdocument data not found in cache', 'error');
        return;
    }

    showLoading(`Retrying subdocument save...`);

    try {
        const response = await fetch("{% url 'admin:chatbot_media_retry_save' %}", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify({
                item_data: cachedData.data, // Use the subdocument data from cache
                company_bot_id: document.getElementById('companyBotSelect').value,
                session_id: sessionId,
                is_subdocument: true,
                parent_media_id: result.media_id
            })
        });

        const retryResult = await response.json();
        if (retryResult.success && retryResult.result) {
            // Update the subdocument result
            updateSubdocumentResult(parentIndex, path, retryResult.result);
            displayResults(saveResults);
            showStatus('Subdocument saved successfully', 'success');
        } else {
            showStatus(`Subdocument retry failed: ${retryResult.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showStatus(`Error retrying subdocument save: ${error.message}`, 'error');
    } finally {
        hideLoading();
    }
}

function updateSubdocumentResult(parentIndex, path, newResult) {
    if (!saveResults[parentIndex]) return;

    function updateResultRecursive(results, targetPath, newResult) {
        for (let i = 0; i < results.length; i++) {
            if (results[i].path === targetPath) {
                results[i] = { ...results[i], ...newResult };
                return true;
            }
            if (results[i].nested_subdocument_results) {
                if (updateResultRecursive(results[i].nested_subdocument_results, targetPath, newResult)) {
                    return true;
                }
            }
        }
        return false;
    }

    if (saveResults[parentIndex].subdocument_results) {
        updateResultRecursive(saveResults[parentIndex].subdocument_results, path, newResult);
    }
}

async function getCachedSubdocument(cacheKey) {
    try {
        const response = await fetch("{% url 'admin:chatbot_media_get_cached_item' %}", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify({ cache_key: cacheKey })
        });

        const result = await response.json();
        if (result.success && result.data) {
            return result.data; // Return just the data part
        }
        return null;
    } catch (error) {
        console.error('Error retrieving cached subdocument:', error);
        return null;
    }
}

function toggleSubdocResults(index) {
    const container = document.getElementById(`subdoc-results-${index}`);
    const arrow = event.currentTarget;

    if (container.classList.contains('expanded')) {
        container.classList.remove('expanded');
        arrow.classList.remove('expanded');
    } else {
        container.classList.add('expanded');
        arrow.classList.add('expanded');
    }
}

// Display save results
function displayResults(results) {
    const successCount = results.filter(r => r.success).length;
    const failedCount = results.filter(r => !r.success).length;

    let totalSubdocs = 0;
    let failedSubdocs = 0;

    document.getElementById('totalFiles').textContent = uploadedFiles.length;
    document.getElementById('finalSuccessCount').textContent = successCount;
    document.getElementById('failedCount').textContent = failedCount;

    // Show/hide retry all button
    const retryAllBtn = document.getElementById('retryAllBtn');
    if (failedCount > 0) {
        retryAllBtn.style.display = 'inline-block';
        retryAllBtn.textContent = `Retry All Failed Saves (${failedCount})`;
    } else {
        retryAllBtn.style.display = 'none';
    }

    const resultsList = document.getElementById('resultsList');
    resultsList.innerHTML = '';

    // In displayResults function, update the results.forEach section:
    results.forEach((result, index) => {
        // Calculate subdocument stats
        let subdocStats = { total: 0, success: 0, failed: 0 };

        function countSubdocs(subdocResults) {
            subdocResults.forEach(subdoc => {
                subdocStats.total++;
                if (subdoc.success) {
                    subdocStats.success++;
                } else {
                    subdocStats.failed++;
                }
                if (subdoc.nested_subdocument_results) {
                    countSubdocs(subdoc.nested_subdocument_results);
                }
            });
        }

        if (result.subdocument_results) {
            countSubdocs(result.subdocument_results);
        }

        const resultItem = document.createElement('div');
        resultItem.className = `save-result-item ${result.success ? 'success' : 'error'}`;

        const hasSubdocs = result.subdocument_results && result.subdocument_results.length > 0;
        const subdocToggle = hasSubdocs ?
        `<svg class="subdoc-toggle-arrow" onclick="toggleSubdocResults(${index})" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m9 18 6-6-6-6"/>
        </svg>` : '';

        const retryButton = !result.success ?
            `<button class="btn retry-btn" onclick="retrySave(${index})">Retry Save</button>` : '';

        // Add subdoc stats display
        const subdocStatsHtml = hasSubdocs ? `
            <div class="subdoc-stats">
                <span class="subdoc-stat success">
                    <span>✓</span>
                    <span>${subdocStats.success}</span>
                </span>
                <span class="subdoc-stat failed">
                    <span>✗</span>
                    <span>${subdocStats.failed}</span>
                </span>
            </div>
        ` : '';

        resultItem.innerHTML = `
            <div class="result-icon">${subdocToggle}${result.success ? '✓' : '✗'}</div>
            <div class="save-result-content">
                <h4>${result.filename}</h4>
                <p>${result.message}</p>
                ${result.success && result.media_id ? `<p>Media ID: ${result.media_id}</p>` : ''}
                ${hasSubdocs ? `
                    <p>Subdocuments: ${subdocStats.success}/${subdocStats.total} saved ${subdocStatsHtml}</p>
                ` : ''}
                ${result.image_results && result.image_results.length > 0 ? `
                    <p>Images: ${result.image_results.filter(i => i.success).length}/${result.image_results.length} saved</p>
                ` : ''}
            </div>
            <div class="save-result-actions">
                ${retryButton}
            </div>
        `;
        resultsList.appendChild(resultItem);

        // Add subdocument results if any
        if (hasSubdocs) {
            const subdocContainer = document.createElement('div');
            subdocContainer.className = 'subdoc-results';
            subdocContainer.id = `subdoc-results-${index}`;
            subdocContainer.innerHTML = renderSubdocumentResults(result.subdocument_results, index);
            resultsList.appendChild(subdocContainer);
        }
    });

    // Update the total failed count to include subdocuments
    let totalFailedSubdocs = 0;
    results.forEach(result => {
        function countFailedSubdocs(subdocResults) {
            subdocResults.forEach(subdoc => {
                if (!subdoc.success) totalFailedSubdocs++;
                if (subdoc.nested_subdocument_results) {
                    countFailedSubdocs(subdoc.nested_subdocument_results);
                }
            });
        }
        if (result.subdocument_results) {
            countFailedSubdocs(result.subdocument_results);
        }
    });

    document.getElementById('failedCount').textContent = failedCount + totalFailedSubdocs;

    // Add skipped files
    const skippedItems = extractedData.filter(item => item.status === FILE_STATUS.SKIPPED);
    skippedItems.forEach(item => {
        const resultItem = document.createElement('div');
        resultItem.className = 'save-result-item';
        resultItem.style.borderLeftColor = '#ff9800';
        resultItem.style.backgroundColor = '#fff8e1';

        resultItem.innerHTML = `
            <div class="result-icon">⊘</div>
            <div class="save-result-content">
                <h4>${item.filename}</h4>
                <p>File was skipped during upload</p>
            </div>
        `;
        resultsList.appendChild(resultItem);
    });

    if (successCount > 0) {
        showStatus(`Successfully saved ${successCount} file(s)!`, 'success');
    }
    if (failedCount > 0) {
        showStatus(`${failedCount} file(s) failed to save. You can retry individual files.`, 'warning');
    }
}

// Clear polling on page unload
window.addEventListener('beforeunload', () => {
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
});

// Initialize
updateFileList();