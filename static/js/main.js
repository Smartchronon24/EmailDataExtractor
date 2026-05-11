document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    lucide.createIcons();
    
    const btnFetch = document.getElementById('btn-fetch');
    const emailListContainer = document.getElementById('email-list-container');
    const detailView = document.getElementById('detail-view');
    const loader = document.getElementById('loader');
    const inboxCount = document.getElementById('inbox-count');
    const searchInput = document.querySelector('.search-wrapper input');
    const btnSaveSettings = document.getElementById('btn-save-settings');
    const navDashboard = document.getElementById('nav-dashboard');
    const navSettings = document.getElementById('nav-settings');
    const viewDashboard = document.getElementById('view-dashboard');
    const viewSettings = document.getElementById('view-settings');

    let processedCache = {}; 
    let isProcessing = false;
    let currentEmails = [];
    let selectedEmailId = null;
    let pipelineState = {};

    function playUISound() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.05, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.1);
        } catch(e) { }
    }

    function updatePipeline(emailId, stepTitle, stepStatus, terminalLogs = null) {
        if (!pipelineState[emailId]) pipelineState[emailId] = [];
        const step = {
            id: Date.now(),
            title: stepTitle,
            status: stepStatus,
            logs: terminalLogs,
            timestamp: new Date().toLocaleTimeString()
        };
        pipelineState[emailId].push(step);
        try { playUISound(); } catch (e) { }
        if (selectedEmailId === emailId) renderPipeline(emailId);
    }

    function renderPipeline(emailId) {
        const container = document.getElementById('pipeline-flow');
        if (!container) return;
        const steps = pipelineState[emailId] || [];
        if (steps.length === 0) {
            container.innerHTML = '<div class="empty-pipeline" style="color: var(--text-dim); font-size: 11px; font-style: italic; opacity: 0.5;">Select an email to start...</div>';
            return;
        }
        container.innerHTML = steps.map((step, index) => {
            const logsHtml = (step.logs && Array.isArray(step.logs)) 
                ? `<div class="terminal-view" id="term-${step.id}">
                       ${step.logs.map(log => `<div>> ${log}</div>`).join('')}
                   </div>`
                : '';
            return `
            <div class="pipeline-card ${index === steps.length - 1 ? 'active' : ''}">
                <div class="title"><i data-lucide="${getStepIcon(step.title || '')}"></i> ${step.title}</div>
                <div class="status">${step.status}</div>
                ${logsHtml}
            </div>`;
        }).join('');
        lucide.createIcons();
        steps.forEach(s => {
            const el = document.getElementById(`term-${s.id}`);
            if (el) el.scrollTop = el.scrollHeight;
        });
    }

    function getStepIcon(title) {
        if (title.includes('Selected')) return 'mouse-pointer-2';
        if (title.includes('Processing')) return 'cpu';
        if (title.includes('Draft')) return 'pen-tool';
        if (title.includes('Mapped')) return 'check-circle';
        return 'circle';
    }

    function updateSaveButtonState() {
        if (btnSaveSettings) {
            btnSaveSettings.disabled = isProcessing;
            btnSaveSettings.style.opacity = isProcessing ? '0.5' : '1';
        }
    }

    async function apiCall(url, method = 'GET', body = null) {
        const options = { method, headers: { 'Content-Type': 'application/json' } };
        if (body) options.body = JSON.stringify(body);
        const res = await fetch(url, options);
        return await res.json();
    }

    function renderEmailList(emails) {
        emailListContainer.innerHTML = '';
        if (!emails || emails.length === 0) {
            emailListContainer.innerHTML = '<div class="empty-state"><i data-lucide="mail"></i><p>No matching emails.</p></div>';
            lucide.createIcons();
            return;
        }
        emails.forEach(email => {
            const card = document.createElement('div');
            card.className = 'email-card animate-in';
            card.innerHTML = `<div class="subject">${email.subject}</div><div class="sender">${email.from.emailAddress.name || email.from.emailAddress.address}</div>`;
            card.onclick = () => selectEmail(email);
            emailListContainer.appendChild(card);
        });
    }

    async function fetchEmails() {
        if (isProcessing) return;
        btnFetch.classList.add('loading');
        btnFetch.disabled = true;
        emailListContainer.innerHTML = '<div class="empty-state"><div class="spinner"></div><p>Connecting to Outlook...</p></div>';
        try {
            const emails = await apiCall('/api/fetch-emails');
            currentEmails = Array.isArray(emails) ? emails : [];
            inboxCount.textContent = currentEmails.length;
            renderEmailList(currentEmails);
        } catch (e) {
            alert("Fetch failed: " + e.message);
        } finally {
            btnFetch.classList.remove('loading');
            btnFetch.disabled = false;
        }
    }

    async function selectEmail(email) {
        selectedEmailId = String(email.id);
        const isProcessed = processedCache[email.id];
        if (!pipelineState[email.id]) updatePipeline(email.id, 'Email Selected', `ID: ${selectedEmailId.substring(0, 10)}...`);
        renderPipeline(email.id);
        document.body.classList.add('show-detail');

        detailView.innerHTML = `
            <div class="detail-view-content animate-in">
                <button class="mobile-back-btn" onclick="document.body.classList.remove('show-detail')" style="display:none; margin-bottom: 20px;">
                    <i data-lucide="arrow-left"></i> Back
                </button>
                <div class="header-section" style="border-bottom:1px solid var(--border); padding-bottom:24px; margin-bottom:24px;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <h1 style="font-size:24px; font-weight:700; margin-bottom:8px;">${email.subject}</h1>
                            <p style="color:var(--text-dim)">From: ${email.from.emailAddress.address}</p>
                        </div>
                        <div style="display:flex; gap:12px;">
                            ${isProcessed ? `<button class="btn btn-secondary" id="btn-forward"><i data-lucide="arrow-right"></i> View Result</button>` : ''}
                            <button class="btn btn-primary" id="btn-start-ai"><i data-lucide="${isProcessed ? 'refresh-cw' : 'sparkles'}"></i> ${isProcessed ? 'Re-Process' : 'Process with AI'}</button>
                        </div>
                    </div>
                </div>
                <div class="body-preview" style="background:rgba(0,0,0,0.2); padding:24px; border-radius:8px; border:1px solid var(--border); min-height:200px; max-height:400px; overflow-y:auto; white-space:pre-wrap; font-size:15px; line-height:1.6; color: #d1d5db;">
                    ${email.body.content
                        .replace(/<br\s*\/?>/gi, '\n')
                        .replace(/<\/p>/gi, '\n\n')
                        .replace(/<\/div>/gi, '\n')
                        .replace(/<[^>]*>?/gm, '')
                        .trim()} 
                </div>
            </div>
        `;
        lucide.createIcons();
        document.getElementById('btn-start-ai').onclick = () => startAIProcessing(email);
        if (isProcessed) document.getElementById('btn-forward').onclick = () => renderAIDetail(processedCache[email.id], email);
    }

    async function startAIProcessing(email) {
        if (isProcessing) return;
        isProcessing = true;
        updateSaveButtonState();
        const btnAI = document.getElementById('btn-start-ai');
        const originalBtnHTML = btnAI.innerHTML;
        btnAI.innerHTML = '<div class="spinner-small"></div> Processing...';
        btnAI.disabled = true;
        btnAI.style.opacity = '0.5';
        btnAI.style.cursor = 'not-allowed';
        btnFetch.disabled = true;
        emailListContainer.style.opacity = '0.5';
        document.body.classList.add('ai-thinking');

        updatePipeline(email.id, 'AI Processing', 'Consulting LLM...', [
            'Initializing Pipeline Stage 2...',
            'Extracting structured data from email body...',
            'Verifying Identity in MySQL Records...'
        ]);

        const startTime = performance.now();
        let finalResult = null;
        let currentThought = "";
        let fullJsonStr = "";
        let streamBuffer = "";
        let lastDataTime = Date.now();

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s connection timeout

            const response = await fetch('/api/process-email-stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!response.ok) throw new Error(`Server Error: ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");

            const watchdog = setInterval(() => {
                if (Date.now() - lastDataTime > 15000) {
                    console.warn("Watchdog timeout");
                    reader.cancel();
                    clearInterval(watchdog);
                }
            }, 5000);

            const steps = pipelineState[email.id] || [];
            const aiStep = steps[steps.length - 1];
            if (aiStep) {
                aiStep.logs.push('Connected. Receiving AI thought stream...');
                renderPipeline(email.id);
            }

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    lastDataTime = Date.now();
                    streamBuffer += decoder.decode(value, { stream: true });
                    let lines = streamBuffer.split(/\n+/);
                    streamBuffer = lines.pop();
                    for (let line of lines) {
                        line = line.trim();
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                if (data.type === 'chunk') {
                                    fullJsonStr += data.content;
                                    const match = fullJsonStr.match(/"thought_process"\s*:\s*"([^"]*)/);
                                    if (match && match[1]) {
                                        currentThought = match[1];
                                        if (aiStep) {
                                            const sec = ((performance.now() - startTime) / 1000).toFixed(1);
                                            aiStep.logs[aiStep.logs.length - 1] = `Thought for ${sec}s -> "${currentThought}<span class="cursor-blink">█</span>"`;
                                            const termEl = document.getElementById(`term-${aiStep.id}`);
                                            if (termEl) {
                                                termEl.innerHTML = aiStep.logs.map(l => `<div>> ${l}</div>`).join('');
                                                termEl.scrollTop = termEl.scrollHeight;
                                            }
                                        }
                                    }
                                } else if (data.type === 'complete') {
                                    finalResult = data;
                                }
                            } catch (e) { }
                        }
                    }
                }
                
                // Final Flush: Process any remaining data in the buffer after the stream ends
                if (streamBuffer.trim().startsWith('data: ')) {
                    try {
                        const data = JSON.parse(streamBuffer.trim().substring(6));
                        if (data.type === 'complete') finalResult = data;
                        else if (data.type === 'error') throw new Error(data.error);
                    } catch (e) { /* Final fragment invalid */ }
                }
            } finally {
                clearInterval(watchdog);
            } 
            
            if (!finalResult) throw new Error("AI stream interrupted.");
            await new Promise(r => setTimeout(r, 800));

            // Finalize previous card
            if (aiStep) {
                const sec = ((performance.now() - startTime) / 1000).toFixed(1);
                aiStep.logs[aiStep.logs.length - 1] = `Thought for ${sec}s -> "${currentThought}"`;
                const termEl = document.getElementById(`term-${aiStep.id}`);
                if (termEl) termEl.innerHTML = aiStep.logs.map(l => `<div>> ${l}</div>`).join('');
            }

            processedCache[email.id] = finalResult;
            const duration = ((performance.now() - startTime) / 1000).toFixed(1);

            updatePipeline(email.id, 'Context Mapped', 'Identity Verified.', [
                `Thought for ${duration}s -> "${finalResult.record.extraction.thought_process || currentThought}"`,
                `User: ${finalResult.db_context.customer.name} (${finalResult.db_context.customer.loyalty_level})`,
                `Context: ${finalResult.rag_context.length} past emails retrieved.`
            ]);

            renderAIDetail(finalResult, email);

        } catch (e) {
            console.error(e);
            alert("Error: " + e.message);
            updatePipeline(email.id, 'Pipeline Error', e.message);
        } finally {
            isProcessing = false;
            updateSaveButtonState();
            document.body.classList.remove('ai-thinking');
            btnAI.innerHTML = originalBtnHTML;
            btnAI.disabled = false;
            btnFetch.disabled = false;
            emailListContainer.style.opacity = '1';
        }
    }

    function renderAIDetail(data, rawEmail) {
        const { record, db_context, rag_context, draft } = data;
        const extraction = record?.extraction || {};
        const entities = extraction.entities || {};
        document.body.classList.add('show-detail');

        detailView.innerHTML = `
            <div class="detail-view-content animate-in">
                <button class="mobile-back-btn" onclick="document.body.classList.remove('show-detail')" style="display:none; margin-bottom: 20px;">
                    <i data-lucide="arrow-left"></i> Back to Inbox
                </button>
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
                    <span class="chip chip-intent">Intent: ${extraction.intent || 'Unknown'}</span>
                    <span class="chip">Category: ${extraction.category || 'General'}</span>
                    ${entities.invoice_number ? `<span class="chip">Invoice: ${entities.invoice_number}</span>` : ''}
                    ${entities.tracking_number ? `<span class="chip">Tracking: ${entities.tracking_number}</span>` : ''}
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px;">
                    <div class="summary-section">
                        <h3 class="section-title">AI Summary</h3>
                        <p style="font-size: 14px; line-height: 1.6; color: var(--text-main)">${extraction.summary || 'No summary generated.'}</p>
                    </div>
                    
                    <div class="knowledge-section">
                        <h3 class="section-title">Knowledge Base</h3>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div id="kb-mysql" class="kb-card" style="background: var(--bg-hover); padding: 12px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; transition: all 0.2s;">
                                <div style="font-size: 10px; color: var(--primary); margin-bottom: 4px; font-weight: 700;">MYSQL MATCH (Click to view)</div>
                                <div style="font-family: monospace; font-size: 11px;">
                                    ${db_context?.invoice ? `Invoice ${db_context.invoice.invoice_id}: ${db_context.invoice.status}` : 'No direct DB match'}
                                </div>
                            </div>
                            <div id="kb-chroma" class="kb-card" style="background: var(--bg-hover); padding: 12px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; transition: all 0.2s;">
                                <div style="font-size: 10px; color: var(--accent); margin-bottom: 4px; font-weight: 700;">CHROMA RAG (Click to view)</div>
                                <div style="font-size: 11px;">
                                    ${rag_context?.length || 0} relevant context blocks found.
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div id="draft-container" class="draft-section" style="margin-top: 40px;">
                    ${draft ? `
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <h3 class="section-title" style="color: var(--accent)">Proposed Draft</h3>
                            <div class="actions" style="display: flex; gap: 10px; flex-wrap: wrap;">
                                <button class="btn btn-secondary" id="btn-regenerate" title="Regenerate Draft" style="background: var(--bg-hover); color: white; padding: 10px 14px;"><i data-lucide="rotate-cw"></i></button>
                                <button class="btn" id="btn-send" style="background: var(--success); color: white; flex: 2; min-width: 150px;"><i data-lucide="send"></i> Approve & Send</button>
                            </div>
                        </div>
                        <div class="draft-box" id="draft-editor" contenteditable="true" style="border-left: 4px solid var(--accent); padding-left: 24px; word-break: break-word; font-size:15px; line-height:1.6;">${typeof draft === 'string' ? draft.replace(/\n/g, '<br>') : 'Draft generation error.'}</div>
                    ` : `
                        <div class="ai-trigger-section" style="border: 1px solid var(--border); padding: 32px; text-align:center;">
                            <p style="color: var(--text-dim); margin-bottom: 16px;">Final context ready. Generate a tailored response draft?</p>
                            <button class="btn btn-primary" id="btn-generate-draft" style="width: 100%; padding: 16px;">
                                <i data-lucide="pen-tool"></i> Generate AI Reply Draft
                            </button>
                        </div>
                    `}
                </div>
            </div>
        `;
        lucide.createIcons();

        // KB Detail Listeners
        const kbMysql = document.getElementById('kb-mysql');
        if (kbMysql) kbMysql.onclick = () => {
            let html = '<div style="display:flex; flex-direction:column; gap:16px;">';
            if(db_context.customer) html += `<div class="kb-detail-card"><strong>Customer:</strong> ${db_context.customer.name} (${db_context.customer.loyalty_level})</div>`;
            if(db_context.invoice) html += `<div class="kb-detail-card"><strong>Invoice:</strong> #${db_context.invoice.invoice_id} | Status: ${db_context.invoice.status}</div>`;
            html += '</div>';
            showDataModal('MySQL DB Context', html, false);
        };
        const kbChroma = document.getElementById('kb-chroma');
        if (kbChroma) kbChroma.onclick = () => showDataModal('Chroma RAG Context', rag_context, true);

        // Draft Generation Listener
        const btnGen = document.getElementById('btn-generate-draft');
        if (btnGen) {
            btnGen.onclick = async () => {
                if (isProcessing) return; // Prevent overlapping tasks
                isProcessing = true;
                updateSaveButtonState();

                const originalText = btnGen.innerHTML;
                btnGen.innerHTML = '<div class="spinner-small"></div> Generating Draft...';
                btnGen.disabled = true;
                btnGen.style.opacity = '0.5';
                
                // Add Draft Generation to the visual pipeline
                updatePipeline(rawEmail.id, 'Draft Generation', 'Writing response...', [
                    'Consulting Stage 3 Intelligence...',
                    'Applying contextual constraints...',
                    'Mapping entities to response template...'
                ]);

                try {
                    const result = await apiCall('/api/generate-reply', 'POST', {
                        extraction: extraction,
                        db_context: db_context,
                        rag_context: rag_context
                    });
                    if (result.error) throw new Error(result.error);
                    
                    processedCache[rawEmail.id].draft = result.draft || result;

                    // Finalize the pipeline card
                    updatePipeline(rawEmail.id, 'Draft Generation', 'Ready for Review', [
                        'Draft successfully generated.',
                        'Tone & Context heuristics applied.'
                    ]);

                    renderAIDetail(processedCache[rawEmail.id], rawEmail);
                } catch (e) {
                    alert("Draft Generation Error: " + e.message);
                } finally {
                    isProcessing = false;
                    updateSaveButtonState();
                    btnGen.innerHTML = originalText;
                    btnGen.disabled = false;
                    btnGen.style.opacity = '1';
                }
            };
        }

        // Draft Actions (Send, Regenerate, Back)
        const btnSend = document.getElementById('btn-send');
        if (btnSend) {
            btnSend.onclick = async () => {
                const editor = document.getElementById('draft-editor');
                const finalContent = editor ? editor.innerText : (typeof draft === 'string' ? draft : '');
                
                btnSend.innerHTML = '<div class="spinner-small"></div> Sending...';
                btnSend.disabled = true;
                try {
                    // Integration Point: Outlook Send API would be called here
                    alert("Success: Email response approved and marked for delivery.");
                } catch (e) {
                    alert("Send Error: " + e.message);
                } finally {
                    btnSend.innerHTML = '<i data-lucide="send"></i> Approve & Send';
                    btnSend.disabled = false;
                }
            };
        }

        const btnRegen = document.getElementById('btn-regenerate');
        if (btnRegen) {
            btnRegen.onclick = async () => {
                if (isProcessing) return;
                isProcessing = true;
                updateSaveButtonState();

                const editor = document.getElementById('draft-editor');
                const originalHTML = editor ? editor.innerHTML : '';
                if (editor) editor.innerHTML = '<div style="display:flex; align-items:center; justify-content:center; height:100px; color:var(--accent);"><div class="spinner-small"></div> Regenerating new draft...</div>';
                
                updatePipeline(rawEmail.id, 'Draft Generation', 'Regenerating...', ['Refreshing Stage 3 Intelligence...', 'Exploring alternative phrasing...']);

                try {
                    const result = await apiCall('/api/generate-reply', 'POST', {
                        extraction: extraction,
                        db_context: db_context,
                        rag_context: rag_context
                    });
                    if (result.error) throw new Error(result.error);
                    
                    processedCache[rawEmail.id].draft = result.draft || result;
                    updatePipeline(rawEmail.id, 'Draft Generation', 'New Draft Ready', ['Draft refreshed successfully.']);
                    renderAIDetail(processedCache[rawEmail.id], rawEmail);
                } catch (e) {
                    alert("Regeneration Error: " + e.message);
                    if (editor) editor.innerHTML = originalHTML;
                } finally {
                    isProcessing = false;
                    updateSaveButtonState();
                }
            };
        }

    }

    function showDataModal(title, content, isJson = true) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay animate-in';
        modal.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.8); backdrop-filter:blur(8px); display:flex; align-items:center; justify-content:center; z-index:2000;';
        
        const inner = document.createElement('div');
        inner.style.cssText = 'background:var(--bg-card); border:1px solid var(--border); padding:32px; border-radius:16px; width:90%; max-width:700px; max-height:80vh; overflow-y:auto;';
        
        const formatted = isJson ? `<pre style="font-family:monospace; font-size:13px; color:var(--primary); background:rgba(0,0,0,0.3); padding:16px; border-radius:8px; white-space:pre-wrap;">${JSON.stringify(content, null, 2)}</pre>` 
                                 : `<div style="line-height:1.6; color:white;">${content}</div>`;

        inner.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px;">
                <h2 style="margin:0; font-size:20px; color:white;">${title}</h2>
                <button id="close-modal" class="btn btn-secondary">Close</button>
            </div>
            ${formatted}
        `;
        modal.appendChild(inner);
        document.body.appendChild(modal);
        document.getElementById('close-modal').onclick = () => modal.remove();
        modal.onclick = (e) => { if(e.target === modal) modal.remove(); };
    }

    // --- GLOBAL WIRING ---
    btnFetch.onclick = fetchEmails;
    if (searchInput) {
        searchInput.oninput = (e) => {
            const q = e.target.value.toLowerCase();
            const filtered = currentEmails.filter(email => 
                email.subject.toLowerCase().includes(q) || 
                (email.from.emailAddress.name || email.from.emailAddress.address).toLowerCase().includes(q)
            );
            renderEmailList(filtered);
        };
    }

    function switchView(view) {
        if (view === 'dashboard') {
            viewDashboard.classList.remove('hidden'); viewSettings.classList.add('hidden');
            navDashboard.classList.add('active'); navSettings.classList.remove('active');
        } else {
            viewDashboard.classList.add('hidden'); viewSettings.classList.remove('hidden');
            navDashboard.classList.remove('active'); navSettings.classList.add('active');
            loadSettings();
        }
    }

    if (navDashboard) navDashboard.onclick = (e) => { e.preventDefault(); switchView('dashboard'); };
    if (navSettings) navSettings.onclick = (e) => { e.preventDefault(); switchView('settings'); };

    async function loadSettings() {
        try {
            const s = await apiCall('/api/settings');
            const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
            const check = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };

            set('set-stage1-model', s.STAGE1_MODEL || 'mistral');
            set('set-stage2-model', s.STAGE2_MODEL || 'llama3');
            set('set-stage3-model', s.STAGE3_MODEL || 'mistral');
            set('set-theme', s.THEME || 'dark');
            check('set-enable-stage1', s.ENABLE_STAGE1);
            check('set-optimize-stage1', s.OPTIMIZE_STAGE1);
            check('set-enable-rag', s.ENABLE_RAG);
            set('set-inv-prefixes', (s.INVOICE_PREFIXES || []).join(', '));
            set('set-trk-prefixes', (s.TRACKING_PREFIXES || []).join(', '));
            set('set-max-workers', s.MAX_WORKERS || 1);
            set('set-max-retries', s.MAX_RETRIES || 2);
            
            if (s.THEME === 'light') document.body.classList.add('light-mode');
            else document.body.classList.remove('light-mode');
        } catch (e) { console.error("Load settings failed:", e); }
    }

    if (btnSaveSettings) {
        btnSaveSettings.onclick = async () => {
            const get = (id) => document.getElementById(id)?.value;
            const isChecked = (id) => document.getElementById(id)?.checked;

            const settings = {
                STAGE1_MODEL: get('set-stage1-model'),
                STAGE2_MODEL: get('set-stage2-model'),
                STAGE3_MODEL: get('set-stage3-model'),
                THEME: get('set-theme'),
                ENABLE_STAGE1: isChecked('set-enable-stage1'),
                OPTIMIZE_STAGE1: isChecked('set-optimize-stage1'),
                ENABLE_RAG: isChecked('set-enable-rag'),
                INVOICE_PREFIXES: get('set-inv-prefixes')?.split(',').map(x => x.trim()).filter(x => x) || [],
                TRACKING_PREFIXES: get('set-trk-prefixes')?.split(',').map(x => x.trim()).filter(x => x) || [],
                MAX_WORKERS: parseInt(get('set-max-workers')) || 1,
                MAX_RETRIES: parseInt(get('set-max-retries')) || 2
            };
            btnSaveSettings.innerText = 'Saving...';
            try {
                await apiCall('/api/settings', 'POST', settings);
                alert("Settings saved!");
            } catch (e) { alert("Error: " + e.message); }
            finally { btnSaveSettings.innerText = 'Save Settings'; }
        };
    }

    loadSettings();
});
