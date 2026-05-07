document.addEventListener('DOMContentLoaded', () => {
    const btnFetch = document.getElementById('btn-fetch');
    const emailListContainer = document.getElementById('email-list-container');
    const detailView = document.getElementById('detail-view');
    const loader = document.getElementById('loader');
    const inboxCount = document.getElementById('inbox-count');

    // Memory cache for processed results
    const processedCache = {};

    // --- API HELPER ---
    async function apiCall(url, method = 'GET', body = null) {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) options.body = JSON.stringify(body);
        
        const response = await fetch(url, options);
        return await response.json();
    }

    // --- FETCH EMAILS ---
    btnFetch.addEventListener('click', async () => {
        btnFetch.classList.add('loading');
        emailListContainer.innerHTML = '<div class="empty-state"><div class="spinner"></div><p>Fetching from Outlook...</p></div>';
        
        const emails = await apiCall('/api/fetch-emails');
        
        if (emails.error) {
            alert("Error: " + emails.error);
            btnFetch.classList.remove('loading');
            return;
        }

        inboxCount.textContent = emails.length;
        emailListContainer.innerHTML = '';
        
        emails.forEach(email => {
            const card = document.createElement('div');
            card.className = 'email-card';
            card.innerHTML = `
                <div class="subject">${email.subject}</div>
                <div class="sender">${email.from.emailAddress.name || email.from.emailAddress.address}</div>
            `;
            card.onclick = () => selectEmail(email);
            emailListContainer.appendChild(card);
        });
        
        btnFetch.classList.remove('loading');
    });

    // --- PHASE 1: SELECT & PREVIEW ---
    async function selectEmail(email) {
        const isProcessed = processedCache[email.id];

        detailView.innerHTML = `
            <div class="detail-view-content">
                <div class="header-section" style="border-bottom: 1px solid var(--border); padding-bottom: 24px; margin-bottom: 24px;">
                    <h1 style="font-size: 24px; font-weight: 700; margin-bottom: 8px;">${email.subject}</h1>
                    <p style="color: var(--text-dim)">From: ${email.from.emailAddress.name || email.from.emailAddress.address} (${email.from.emailAddress.address})</p>
                    <p style="color: var(--text-dim); font-size: 12px; margin-top: 4px;">Received: ${new Date(email.receivedDateTime).toLocaleString()}</p>
                </div>

                <div class="body-preview" style="background: rgba(0,0,0,0.2); padding: 24px; border-radius: 8px; border: 1px solid var(--border); min-height: 200px; max-height: 450px; overflow-y: auto; margin-bottom: 32px; white-space: pre-wrap; font-size: 15px; line-height: 1.6; color: #d1d5db;">
                    ${email.body.content
                        .replace(/<br\s*\/?>/gi, '\n')
                        .replace(/<\/p>/gi, '\n\n')
                        .replace(/<\/div>/gi, '\n')
                        .replace(/<[^>]*>?/gm, '')
                        .trim()} 
                </div>

                <div class="ai-trigger-section" style="display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 40px; border: 2px dashed var(--border); border-radius: 12px;">
                    <i data-lucide="${isProcessed ? 'check-circle' : 'sparkles'}" style="width: 32px; height: 32px; color: var(--primary)"></i>
                    <div style="text-align: center;">
                        <h3 style="margin-bottom: 4px;">${isProcessed ? 'Already Analyzed' : 'Ready to automate?'}</h3>
                        <p style="color: var(--text-dim); font-size: 14px;">${isProcessed ? 'You can view the existing AI results or re-process it.' : 'Let Llama 3 and ChromaDB analyze this email and draft a reply.'}</p>
                    </div>
                    <div style="display: flex; gap: 16px;">
                        <button class="btn btn-primary" id="btn-start-ai" style="padding: 12px 32px; font-size: 16px;">
                            <i data-lucide="refresh-cw"></i> ${isProcessed ? 'Re-Process' : 'Process with AI'}
                        </button>
                        ${isProcessed ? `
                        <button class="btn" id="btn-forward" style="padding: 12px 32px; font-size: 16px; background: var(--bg-hover); color: white;">
                            <i data-lucide="arrow-right"></i> View Result
                        </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
        
        lucide.createIcons();

        document.getElementById('btn-start-ai').onclick = () => startAIProcessing(email);
        if (isProcessed) {
            document.getElementById('btn-forward').onclick = () => renderAIDetail(processedCache[email.id], email);
        }
    }

    // --- PHASE 2: RUN AI PIPELINE ---
    async function startAIProcessing(email) {
        const btnAI = document.getElementById('btn-start-ai');
        const originalBtnHTML = btnAI.innerHTML;

        // 1. Lock global interactions
        btnFetch.disabled = true;
        btnFetch.style.opacity = '0.5';
        emailListContainer.style.pointerEvents = 'none';
        emailListContainer.style.opacity = '0.6';
        
        // 2. Show button-level loader
        btnAI.disabled = true;
        btnAI.innerHTML = '<div class="spinner" style="width:18px; height:18px; border-width:2px; margin-right:8px;"></div> AI Analyzing...';
        
        // Also show panel loader for extra visibility
        loader.classList.remove('hidden');

        const result = await apiCall('/api/process-email', 'POST', { email });
        
        // 3. Unlock
        loader.classList.add('hidden');
        btnFetch.disabled = false;
        btnFetch.style.opacity = '1';
        emailListContainer.style.pointerEvents = 'auto';
        emailListContainer.style.opacity = '1';
        
        if (result.error) {
            alert("Error: " + result.error);
            btnAI.disabled = false;
            btnAI.innerHTML = originalBtnHTML;
            return;
        }

        // Store in cache for fast navigation
        processedCache[email.id] = result;

        renderAIDetail(result, email);
    }

    function renderAIDetail(data, rawEmail) {
        const { record, db_context, rag_context, draft } = data;
        const extraction = record.extraction;

        detailView.innerHTML = `
            <div class="detail-view-content animate-in">
                <div class="header-section">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <h1 style="font-size: 24px; font-weight: 700; margin-bottom: 8px;">${rawEmail.subject}</h1>
                            <p style="color: var(--text-dim)">From: ${rawEmail.from.emailAddress.address}</p>
                        </div>
                        <div class="status-badge" style="background: var(--primary-glow); color: var(--primary); padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">
                            <i data-lucide="check" style="width:12px; height:12px; display:inline; vertical-align:middle;"></i> AI CONTEXT READY
                        </div>
                    </div>
                </div>

                <div class="entity-chips">
                    <span class="chip chip-intent">Intent: ${extraction.intent}</span>
                    <span class="chip">Category: ${extraction.category}</span>
                    ${extraction.entities.invoice_number ? `<span class="chip">Invoice: ${extraction.entities.invoice_number}</span>` : ''}
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px;">
                    <div class="summary-section">
                        <h3 class="section-title">AI Summary</h3>
                        <p style="font-size: 14px; line-height: 1.6; color: var(--text-main)">${extraction.summary}</p>
                    </div>
                    
                    <div class="knowledge-section">
                        <h3 class="section-title">Knowledge Base</h3>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div style="background: var(--bg-hover); padding: 12px; border-radius: 8px;">
                                <div style="font-size: 10px; color: var(--primary); margin-bottom: 4px; font-weight: 700;">MYSQL MATCH</div>
                                <div style="font-family: monospace; font-size: 11px;">
                                    ${db_context.invoice ? `Invoice ${db_context.invoice.invoice_id}: ${db_context.invoice.status}` : 'No direct DB match'}
                                </div>
                            </div>
                            <div style="background: var(--bg-hover); padding: 12px; border-radius: 8px;">
                                <div style="font-size: 10px; color: var(--accent); margin-bottom: 4px; font-weight: 700;">CHROMA RAG</div>
                                <div style="font-size: 11px;">
                                    ${rag_context.length} relevant context blocks found.
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div id="draft-container" class="draft-section" style="margin-top: 40px;">
                    ${draft ? `
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <h3 class="section-title" style="color: var(--accent)">Proposed Draft</h3>
                            <div class="actions" style="display: flex; gap: 12px;">
                                <button class="btn btn-secondary" id="btn-back" style="background: var(--bg-hover); color: white;">Back</button>
                                <button class="btn" id="btn-send" style="background: var(--success); color: white;"><i data-lucide="send"></i> Approve & Send</button>
                            </div>
                        </div>
                        <div class="draft-box" id="draft-editor" contenteditable="true" style="border-left: 4px solid var(--accent); padding-left: 24px;">${draft.replace(/\n/g, '<br>')}</div>
                    ` : `
                        <div class="ai-trigger-section" style="border: 1px solid var(--border); padding: 32px;">
                            <button class="btn btn-primary" id="btn-generate-draft" style="width: 100%; padding: 16px;">
                                <i data-lucide="pen-tool"></i> Generate AI Reply Draft
                            </button>
                        </div>
                    `}
                </div>
            </div>
        `;
        
        lucide.createIcons();

        // Phase 2 Trigger: Generate Draft
        const btnGen = document.getElementById('btn-generate-draft');
        if (btnGen) {
            btnGen.onclick = async () => {
                btnGen.disabled = true;
                btnGen.innerHTML = '<div class="spinner" style="width:18px; height:18px;"></div> Generating Draft...';
                
                const result = await apiCall('/api/generate-reply', 'POST', {
                    extraction, db_context, rag_context
                });
                
                if (result.draft) {
                    // Update cache and re-render
                    processedCache[rawEmail.id].draft = result.draft;
                    renderAIDetail(processedCache[rawEmail.id], rawEmail);
                } else {
                    alert("Error: " + result.error);
                    btnGen.disabled = false;
                    btnGen.innerHTML = '<i data-lucide="pen-tool"></i> Generate AI Reply Draft';
                }
            };
        }

        // Send Logic
        const btnSend = document.getElementById('btn-send');
        if (btnSend) {
            btnSend.onclick = async () => {
                const content = document.getElementById('draft-editor').innerText;
                btnSend.innerHTML = '<div class="spinner" style="width:16px; height:16px;"></div> Sending...';
                btnSend.disabled = true;

                const response = await apiCall('/api/send-email', 'POST', {
                    message_id: rawEmail.id,
                    content: content
                });

                if (response.success) {
                    alert("Email sent successfully!");
                    detailView.innerHTML = '<div class="empty-state"><i data-lucide="check-circle" style="color:var(--success)"></i><p>Email Sent!</p></div>';
                    lucide.createIcons();
                    btnFetch.click();
                } else {
                    alert("Error sending email: " + response.error);
                    btnSend.innerHTML = '<i data-lucide="send"></i> Approve & Send';
                    btnSend.disabled = false;
                }
            };
        }

        // Back button
        const btnBack = document.getElementById('btn-back');
        if (btnBack) {
            btnBack.onclick = () => selectEmail(rawEmail);
        }
    }
});
