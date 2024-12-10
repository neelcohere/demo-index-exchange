// static/js/main.js

const summaryCache = {};

// Function to highlight selected row
function highlightSelectedRow(row) {
    document.querySelectorAll('tr').forEach(tr => {
        tr.classList.remove('bg-blue-50');
    });
    row.classList.add('bg-blue-50');
}

// Function to attach event listeners to log cards
function attachLogCardListeners() {
    console.log('Attaching log card listeners');
    const logCards = document.querySelectorAll('.log-card');
    console.log('Found log cards:', logCards.length);
    
    logCards.forEach(card => {
        card.addEventListener('click', async function() {
            const logId = this.getAttribute('data-log-id');
            console.log('Log card clicked:', logId);
            await showLogDetails(logId);
        });
    });
}

// HTMX after swap event listener
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'chain-details') {
        console.log('Chain details loaded, initializing...');
        attachLogCardListeners();
    }
});

async function showLogDetails(logId) {
    console.log('showLogDetails called with logId:', logId);
    
    const logElement = document.querySelector(`[data-log-id="${logId}"]`);
    console.log('logElement found:', logElement);
    
    if (!logElement) {
        console.log('No element found with data-log-id:', logId);
        return;
    }

    try {
        const logDataStr = logElement.getAttribute('data-log-data');
        const logData = JSON.parse(logDataStr);
        const timestamp = logElement.getAttribute('data-log-timestamp');

        // Show the details panel
        const logDetailsElement = document.getElementById('log-details');
        logDetailsElement.classList.remove('hidden');
        
        // Update initial fields
        document.getElementById('log-id').textContent = logId;
        document.getElementById('log-data').textContent = JSON.stringify(logData, null, 2);
        document.getElementById('log-timestamp').textContent = 
            `Timestamp: ${new Date(timestamp).toLocaleString()}`;

        // Show loading state, hide summary text
        const loadingElement = document.getElementById('summary-loading');
        const summaryTextElement = document.getElementById('summary-text');

        if (loadingElement) loadingElement.classList.remove('hidden');
        if (summaryTextElement) summaryTextElement.textContent = '';

        try {
            let summary;
            
            // Check cache first
            if (summaryCache[logId]) {
                console.log('Using cached summary for', logId);
                summary = summaryCache[logId];
            } else {
                // If not in cache, make API call
                console.log('Generating new summary for', logId);
                const response = await fetch('/api/generate-summary', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ logData: logData })
                });

                if (!response.ok) {
                    throw new Error('Failed to generate summary');
                }

                const data = await response.json();
                summary = data.summary;
                
                // Store in cache
                summaryCache[logId] = summary;
            }

            // Hide loading spinner and show summary
            if (loadingElement) loadingElement.classList.add('hidden');
            if (summaryTextElement) {
                summaryTextElement.classList.remove('hidden');
                summaryTextElement.textContent = summary;
            }

        } catch (error) {
            console.error('Error generating summary:', error);
            if (loadingElement) loadingElement.classList.add('hidden');
            if (summaryTextElement) {
                summaryTextElement.classList.remove('hidden');
                summaryTextElement.textContent = 'Error generating summary. Please try again.';
            }
        }

    } catch (error) {
        console.error('Error in showLogDetails:', error);
    }
}

window.showAlertModal = function() {
    const modal = document.getElementById('alert-modal');
    if (modal) {
        modal.classList.remove('hidden');
    } else {
        console.error('Alert modal element not found');
    }
}

window.hideAlertModal = function() {
    const modal = document.getElementById('alert-modal');
    if (modal) {
        modal.classList.add('hidden');
    } else {
        console.error('Alert modal element not found');
    }
}

window.copyAlertToClipboard = function() {
    const alertContent = document.querySelector('.alert-content');
    if (!alertContent) {
        console.error('Alert content element not found');
        return;
    }
    
    navigator.clipboard.writeText(alertContent.innerText)
        .then(() => showToast('Alert copied to clipboard'))
        .catch(error => {
            console.error('Failed to copy to clipboard:', error);
            showToast('Failed to copy to clipboard');
        });
}

window.sendAlert = async function() {
    const modal = document.getElementById('alert-modal');
    if (!modal) {
        console.error('Alert modal element not found');
        return;
    }

    try {
        // Show loading state
        const sendButton = modal.querySelector('button:last-child');
        const originalText = sendButton.innerHTML;
        sendButton.innerHTML = '<i class="ri-loader-4-line animate-spin mr-2"></i>Sending...';
        sendButton.disabled = true;

        // Get the content div
        const contentDiv = modal.querySelector('.alert-content').cloneNode(true);

        // Add some basic styling for PDF
        const htmlContent = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Ad Render Failure Report</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; }
                    .section { margin-bottom: 20px; }
                    .section-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
                    .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
                    .timeline-item { margin-bottom: 15px; padding-left: 20px; border-left: 2px solid #e5e7eb; }
                    .timeline-title { font-weight: bold; }
                    .timeline-time { color: #666; font-size: 0.9em; }
                    .timeline-summary { margin-top: 5px; color: #444; }
                    .recommendations { margin-top: 20px; }
                    .recommendations li { margin-bottom: 5px; }
                </style>
            </head>
            <body>
                ${contentDiv.outerHTML}
            </body>
            </html>
        `;

        // Send to server
        const response = await fetch('/api/send-alert', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ html: htmlContent })
        });

        if (!response.ok) {
            throw new Error('Failed to send email');
        }

        // Show success message
        showToast('Alert email sent successfully');
        hideAlertModal();

    } catch (error) {
        console.error('Error sending alert:', error);
        showToast('Failed to send email. Please try again.');
    } finally {
        // Reset button state
        if (sendButton) {
            sendButton.innerHTML = originalText;
            sendButton.disabled = false;
        }
    }
}

function formatRecommendations(recommendations) {
    // Split by priority sections
    const sections = recommendations.split('##').filter(Boolean);
    
    return sections.map(section => {
        const [priority, ...content] = section.trim().split(':');
        const recommendations = content.join(':') // Rejoin in case there were colons in the content
            .split(/(?=\d\.)/)  // Split on numbered points
            .filter(Boolean)    // Remove empty strings
            .map(rec => rec.trim());

        return `
            <div class="recommendation-section">
                <h5 class="text-lg font-semibold mb-3 ${getPriorityColor(priority)}">
                    ${priority}
                </h5>
                <ul class="space-y-4">
                    ${recommendations.map(rec => {
                        const [number, ...text] = rec.split('.');
                        const [recommendation, impact] = text.join('.').split('Impact:');
                        return `
                            <li class="ml-4">
                                <div class="recommendation-content">
                                    <p class="mb-2">${recommendation.trim()}</p>
                                    ${impact ? `
                                        <p class="text-sm text-gray-600 mt-1">
                                            <span class="font-medium">Impact:</span> 
                                            ${impact.trim()}
                                        </p>
                                    ` : ''}
                                </div>
                            </li>
                        `;
                    }).join('')}
                </ul>
            </div>
        `;
    }).join('<div class="border-t my-4"></div>');  // Add separator between sections
}

function getPriorityColor(priority) {
    if (priority.toLowerCase().includes('high')) return 'text-red-600';
    if (priority.toLowerCase().includes('medium')) return 'text-yellow-600';
    if (priority.toLowerCase().includes('low')) return 'text-green-600';
    return 'text-gray-600';
}

window.showAlertModal = async function() {
    const modal = document.getElementById('alert-modal');
    if (!modal) {
        console.error('Alert modal element not found');
        return;
    }

    // Show the modal
    modal.classList.remove('hidden');

    // Gather all summaries from cache or log data
    const logCards = document.querySelectorAll('.log-card');
    const summaries = {};
    
    for (const card of logCards) {
        const logId = card.getAttribute('data-log-id');
        const logTitle = card.querySelector('.font-bold').textContent;
        
        // Get summary from cache if available, otherwise use default summary
        summaries[logTitle] = summaryCache[logId] || card.getAttribute('data-log-summary');
    }

    try {
        // Generate recommendations
        const response = await fetch('/api/generate-recommendations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ summaries })
        });

        if (!response.ok) {
            throw new Error('Failed to generate recommendations');
        }

        const data = await response.json();
        console.log('Received recommendations:', data.recommendations);
        
        // Update the recommendations section in the modal with formatted content
        const recommendationsSection = modal.querySelector('#recommended-actions');
        if (recommendationsSection) {
            recommendationsSection.innerHTML = formatRecommendations(data.recommendations);
        } else {
            console.error('#recommended-actions element not found in modal');
        }

    } catch (error) {
        console.error('Error generating recommendations:', error);
    }

    // Populate summaries in timeline
    const summaryPlaceholders = modal.querySelectorAll('.summary-placeholder');
    summaryPlaceholders.forEach(placeholder => {
        const logId = placeholder.dataset.logId;
        
        if (summaryCache[logId]) {
            placeholder.textContent = summaryCache[logId];
        } else {
            const logCard = document.querySelector(`[data-log-id="${logId}"]`);
            if (logCard) {
                placeholder.textContent = logCard.getAttribute('data-log-summary');
            }
        }
    });
}

function hideAlertModal() {
    const modal = document.getElementById('alert-modal');
    if (modal) {
        modal.classList.add('hidden');
    } else {
        console.error('Alert modal element not found');
    }
}

window.copyAlertToClipboard = function() {
    const modal = document.getElementById('alert-modal');
    if (!modal) {
        console.error('Alert modal element not found');
        return;
    }

    // Create a formatted version of the content
    const publisherInfo = modal.querySelector('.bg-gray-50').textContent;
    const timeline = Array.from(modal.querySelectorAll('#alert-timeline > div')).map(item => {
        const title = item.querySelector('.font-medium').textContent;
        const timestamp = item.querySelector('.text-gray-500').textContent;
        const summary = item.querySelector('.summary-placeholder').textContent;
        return `${title} (${timestamp})\n${summary}`;
    }).join('\n\n');

    const technicalDetails = Array.from(modal.querySelectorAll('.bg-gray-50:last-of-type div'))
        .map(div => div.textContent).join('\n');

    const formattedContent = `Alert: Render Failure Detected\n\n${publisherInfo}\n\nEvent Timeline:\n${timeline}\n\nTechnical Details:\n${technicalDetails}`;

    navigator.clipboard.writeText(formattedContent)
        .then(() => showToast('Alert copied to clipboard'))
        .catch(error => {
            console.error('Failed to copy to clipboard:', error);
            showToast('Failed to copy to clipboard');
        });
}

function sendAlert() {
    showToast('Alert email sent successfully');
    hideAlertModal();
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'fixed bottom-4 right-4 bg-gray-800 text-white px-6 py-3 rounded-lg shadow-lg transform transition-all duration-300';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function attachRowHighlightListeners() {
    const rows = document.querySelectorAll('tr[hx-get]');
    rows.forEach(row => {
        row.addEventListener('click', function() {
            highlightSelectedRow(this);
        });
    });
}

// Optional: Add a function to clear the cache if needed
window.clearSummaryCache = function() {
    Object.keys(summaryCache).forEach(key => delete summaryCache[key]);
    console.log('Summary cache cleared');
}

// Add this to help with debugging
document.addEventListener('DOMContentLoaded', () => {
    console.log('main.js loaded');
    attachRowHighlightListeners();
});