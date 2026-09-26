/**
 * Regulatory Copilot - Embeddable Floating & Split-View Widget Library
 * Vanilla JS implementation for 50% side drawer compliance copilot in clean white theme.
 */

(function (global) {
    const DEFAULT_API_BASE = "http://127.0.0.1:8000";

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function determineDateStatus(item) {
        let status = "upcoming";
        let dateStr = "";
        let provision = "";

        if (typeof item === "object" && item !== null) {
            provision = item.provision || item.description || item.title || "";
            dateStr = item.date || item.effective_date || "";
            status = item.status || "";
        } else {
            const str = String(item);
            provision = str;
            dateStr = str;
        }

        const lowerStr = (status + " " + provision + " " + dateStr).toLowerCase();

        if (status) {
            status = status.toLowerCase();
            if (status.includes("force") || status.includes("active") || status.includes("enforced")) return { status: "in-force", label: "In Force", provision, dateStr };
            if (status.includes("phase") || status.includes("staggered")) return { status: "phased", label: "Phased", provision, dateStr };
            if (status.includes("upcoming") || status.includes("future") || status.includes("pending")) return { status: "upcoming", label: "Upcoming", provision, dateStr };
        }

        if (lowerStr.includes("phased") || lowerStr.includes("phase")) {
            return { status: "phased", label: "Phased", provision, dateStr };
        }
        if (lowerStr.includes("in force") || lowerStr.includes("enforced") || lowerStr.includes("effective immediately")) {
            return { status: "in-force", label: "In Force", provision, dateStr };
        }

        const parsedDate = Date.parse(dateStr);
        if (!isNaN(parsedDate)) {
            if (parsedDate <= Date.now()) {
                return { status: "in-force", label: "In Force", provision, dateStr };
            } else {
                return { status: "upcoming", label: "Upcoming", provision, dateStr };
            }
        }

        return { status: "upcoming", label: "Upcoming", provision, dateStr };
    }

    function parseTeamItem(item) {
        if (typeof item === "object" && item !== null) {
            return {
                name: item.name || item.team || "Team",
                reason: item.reason || item.description || item.impact || "Responsible for regulatory compliance execution."
            };
        }
        const str = String(item);
        if (str.includes(":")) {
            const parts = str.split(":");
            return {
                name: parts[0].trim(),
                reason: parts.slice(1).join(":").trim()
            };
        }
        return {
            name: str.trim(),
            reason: `Directly impacted by regulatory provisions for ${str.trim()}.`
        };
    }

    class RegulatoryCopilotWidget {
        constructor(container, options = {}) {
            this.container = typeof container === "string" ? document.querySelector(container) : container;
            this.options = options;
            this.apiBase = (options.apiBase || DEFAULT_API_BASE).replace(/\/$/, "");
            this.mode = options.mode || "drawer"; // "drawer" or "inline"
            this.isOpen = false;

            this.init();
        }

        init() {
            if (this.mode === "drawer") {
                this.setupDrawer();
            } else if (this.container) {
                this.renderInlineTemplate();
                this.bindElements(this.container);
                this.bindEvents();
                this.checkHealth();
            }
        }

        setupDrawer() {
            // Create backdrop overlay
            this.overlay = document.createElement("div");
            this.overlay.className = "rc-drawer-overlay";
            document.body.appendChild(this.overlay);

            // Create drawer panel (50% screen width)
            this.panel = document.createElement("div");
            this.panel.className = "rc-drawer-panel";
            this.renderDrawerTemplate(this.panel);
            document.body.appendChild(this.panel);

            // Create floating trigger button at bottom-right
            if (this.options.showTrigger !== false) {
                this.triggerBtn = document.createElement("button");
                this.triggerBtn.className = "rc-floating-trigger";
                this.triggerBtn.innerHTML = `
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2L3 7V12C3 17.523 7.02 22.5 12 24C16.98 22.5 21 17.523 21 12V7L12 2Z"/>
                        <path d="M9 12L11 14L15 10"/>
                    </svg>
                    <span>Ask Copilot</span>
                    <span class="rc-floating-badge">AI</span>
                `;
                document.body.appendChild(this.triggerBtn);

                this.triggerBtn.addEventListener("click", () => this.toggle());
            }

            this.overlay.addEventListener("click", () => this.close());

            this.bindElements(this.panel);
            this.bindEvents();
            this.checkHealth();
        }

        renderDrawerTemplate(target) {
            target.innerHTML = `
                <div class="rc-widget">
                    <!-- Widget Header -->
                    <div class="rc-header">
                        <div class="rc-brand">
                            <div class="rc-logo-icon">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M12 2L3 7V12C3 17.523 7.02 22.5 12 24C16.98 22.5 21 17.523 21 12V7L12 2Z"/>
                                    <path d="M9 12L11 14L15 10"/>
                                </svg>
                            </div>
                            <div class="rc-brand-text">
                                <span class="rc-title">Regulatory Copilot</span>
                                <span class="rc-subtitle">Compliance RAG Engine</span>
                            </div>
                        </div>
                        <div class="rc-header-controls">
                            <div class="rc-status-pill" id="rcStatusPill" title="Click to test /api/health">
                                <span class="rc-status-dot" id="rcStatusDot"></span>
                                <span class="rc-status-text" id="rcStatusText">Connecting...</span>
                            </div>
                            <button type="button" class="rc-close-btn" id="rcCloseBtn" title="Close Panel">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <line x1="18" y1="6" x2="6" y2="18"/>
                                    <line x1="6" y1="6" x2="18" y2="18"/>
                                </svg>
                            </button>
                        </div>
                    </div>

                    <!-- Scrollable Content Body -->
                    <div class="rc-content-area">
                        <!-- Query Form -->
                        <form class="rc-query-form" id="rcForm">
                            <div class="rc-input-group">
                                <textarea id="rcInput" class="rc-textarea" placeholder="Ask about regulatory circulars, LCR, RBI/SEBI norms..." rows="2" required></textarea>
                                <div class="rc-form-actions">
                                    <div class="rc-presets">
                                        <span class="rc-presets-label">Quick:</span>
                                        <button type="button" class="rc-chip-preset" data-query="What are the effective dates for Liquidity Coverage Ratio compliance?">LCR Dates</button>
                                        <button type="button" class="rc-chip-preset" data-query="Which teams are impacted by new SEBI circulars?">Impacted Teams</button>
                                        <button type="button" class="rc-chip-preset" data-query="Summarize RBI capital adequacy and NBFC norms.">RBI NBFC</button>
                                    </div>
                                    <button type="submit" id="rcSubmitBtn" class="rc-btn-submit">
                                        <span>Ask Copilot</span>
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <line x1="22" y1="2" x2="11" y2="13"/>
                                            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                                        </svg>
                                    </button>
                                </div>
                            </div>
                        </form>

                        <!-- Content Display Area -->
                        <div class="rc-body" id="rcBody">
                            <!-- Placeholder State -->
                            <div class="rc-placeholder" id="rcPlaceholder">
                                <div class="rc-placeholder-icon">
                                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <circle cx="12" cy="12" r="10"/>
                                        <line x1="12" y1="8" x2="12" y2="12"/>
                                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                                    </svg>
                                </div>
                                <h3>Regulatory Copilot Active</h3>
                                <p>Submit a query above to fetch compliance synthesis, circular citations, timeline statuses, and impacted teams.</p>
                            </div>

                            <!-- Loading State -->
                            <div class="rc-loading" id="rcLoading" style="display: none;">
                                <div class="rc-spinner"></div>
                                <p class="rc-loading-text">Analyzing circulars & verifying regulatory claims via Gemini...</p>
                            </div>

                            <!-- Result Response View -->
                            <div class="rc-response-card" id="rcResponseCard" style="display: none;">
                                <!-- Warning Banner for Unverified Claims -->
                                <div class="rc-warning-banner" id="rcWarningBanner" style="display: none;">
                                    <div class="rc-warning-header">
                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                                            <line x1="12" y1="9" x2="12" y2="13"/>
                                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                                        </svg>
                                        <span>Unverified Claims Warning</span>
                                    </div>
                                    <ul class="rc-warning-list" id="rcWarningList"></ul>
                                </div>

                                <!-- Answer Section -->
                                <div class="rc-section">
                                    <div class="rc-section-header">
                                        <h4 class="rc-section-title">Compliance Synthesis</h4>
                                        <span class="rc-timestamp" id="rcTimestamp"></span>
                                    </div>
                                    <div class="rc-answer-p" id="rcAnswerText"></div>
                                    <div class="rc-confidence-note" id="rcConfidenceNote" style="display: none;"></div>
                                </div>

                                <!-- Citations Row -->
                                <div class="rc-section" id="rcCitationsSection" style="display: none;">
                                    <h4 class="rc-section-title">Circular Citations</h4>
                                    <div class="rc-citations-row" id="rcCitationsRow"></div>
                                </div>

                                <!-- Effective Dates Horizontal Timeline -->
                                <div class="rc-section" id="rcTimelineSection" style="display: none;">
                                    <h4 class="rc-section-title">Effective Dates Timeline</h4>
                                    <div class="rc-timeline-track" id="rcTimelineTrack"></div>
                                </div>

                                <!-- Impacted Teams Tags -->
                                <div class="rc-section" id="rcTeamsSection" style="display: none;">
                                    <h4 class="rc-section-title">Impacted Teams</h4>
                                    <div class="rc-teams-row" id="rcTeamsRow"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        renderInlineTemplate() {
            this.container.classList.add("rc-widget-inline");
            this.renderDrawerTemplate(this.container);
        }

        bindElements(root) {
            this.root = root;
            this.form = root.querySelector("#rcForm");
            this.input = root.querySelector("#rcInput");
            this.submitBtn = root.querySelector("#rcSubmitBtn");
            this.statusPill = root.querySelector("#rcStatusPill");
            this.statusDot = root.querySelector("#rcStatusDot");
            this.statusText = root.querySelector("#rcStatusText");
            this.closeBtn = root.querySelector("#rcCloseBtn");

            this.placeholder = root.querySelector("#rcPlaceholder");
            this.loading = root.querySelector("#rcLoading");
            this.responseCard = root.querySelector("#rcResponseCard");

            this.warningBanner = root.querySelector("#rcWarningBanner");
            this.warningList = root.querySelector("#rcWarningList");
            this.answerText = root.querySelector("#rcAnswerText");
            this.confidenceNote = root.querySelector("#rcConfidenceNote");
            this.timestamp = root.querySelector("#rcTimestamp");

            this.citationsSection = root.querySelector("#rcCitationsSection");
            this.citationsRow = root.querySelector("#rcCitationsRow");

            this.timelineSection = root.querySelector("#rcTimelineSection");
            this.timelineTrack = root.querySelector("#rcTimelineTrack");

            this.teamsSection = root.querySelector("#rcTeamsSection");
            this.teamsRow = root.querySelector("#rcTeamsRow");
        }

        bindEvents() {
            this.form.addEventListener("submit", (e) => {
                e.preventDefault();
                this.submitQuery();
            });

            if (this.closeBtn) {
                this.closeBtn.addEventListener("click", () => this.close());
            }

            this.statusPill.addEventListener("click", () => this.checkHealth());

            this.root.querySelectorAll(".rc-chip-preset").forEach(presetBtn => {
                presetBtn.addEventListener("click", () => {
                    this.input.value = presetBtn.dataset.query;
                    this.submitQuery();
                });
            });
        }

        open() {
            if (this.panel) this.panel.classList.add("is-open");
            if (this.overlay) this.overlay.classList.add("is-open");
            this.isOpen = true;
            if (this.input) setTimeout(() => this.input.focus(), 150);
        }

        close() {
            if (this.panel) this.panel.classList.remove("is-open");
            if (this.overlay) this.overlay.classList.remove("is-open");
            this.isOpen = false;
        }

        toggle() {
            if (this.isOpen) {
                this.close();
            } else {
                this.open();
            }
        }

        async checkHealth() {
            this.statusDot.className = "rc-status-dot rc-status-unknown";
            this.statusText.textContent = "Connecting...";
            try {
                const res = await fetch(`${this.apiBase}/api/health`, { method: "GET" });
                if (res.ok) {
                    const data = await res.json();
                    if (data.status === "ok") {
                        this.statusDot.className = "rc-status-dot rc-status-ok";
                        this.statusText.textContent = "API Ready";
                        return;
                    }
                }
                throw new Error(`HTTP ${res.status}`);
            } catch (err) {
                this.statusDot.className = "rc-status-dot rc-status-error";
                this.statusText.textContent = "Disconnected";
            }
        }

        async submitQuery(customQuery) {
            const queryText = (customQuery || this.input.value).trim();
            if (!queryText) return;

            this.input.value = queryText;
            this.placeholder.style.display = "none";
            this.responseCard.style.display = "none";
            this.loading.style.display = "flex";
            this.submitBtn.disabled = true;

            try {
                const res = await fetch(`${this.apiBase}/api/query`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    body: JSON.stringify({ query: queryText, question: queryText })
                });

                if (!res.ok) {
                    throw new Error(`Server returned status ${res.status}`);
                }

                const data = await res.json();
                this.renderResponse(data);
            } catch (err) {
                console.error("Regulatory Copilot Query Error:", err);
                this.loading.style.display = "none";
                this.placeholder.style.display = "none";
                this.responseCard.style.display = "block";

                this.answerText.innerHTML = `
                    <div class="rc-error-box">
                        <strong>API Error:</strong> ${escapeHtml(err.message)}. Ensure backend server is running on ${escapeHtml(this.apiBase)}.
                    </div>
                `;
                this.warningBanner.style.display = "none";
                this.citationsSection.style.display = "none";
                this.timelineSection.style.display = "none";
                this.teamsSection.style.display = "none";
                this.confidenceNote.style.display = "none";
                this.timestamp.textContent = "Failed";
            } finally {
                this.submitBtn.disabled = false;
            }
        }

        renderResponse(data) {
            this.loading.style.display = "none";
            this.responseCard.style.display = "block";
            this.timestamp.textContent = new Date().toLocaleTimeString();

            // 1. Answer Paragraph
            const formattedAnswer = escapeHtml(data.answer || "No response generated.");
            this.answerText.innerHTML = `<p>${formattedAnswer.replace(/\n/g, '<br>')}</p>`;

            // Confidence Note
            if (data.confidence_note) {
                this.confidenceNote.style.display = "block";
                this.confidenceNote.textContent = `Note: ${data.confidence_note}`;
            } else {
                this.confidenceNote.style.display = "none";
            }

            // 2. Unverified Claims Banner
            const unverified = data.unverified_claims || [];
            if (Array.isArray(unverified) && unverified.length > 0) {
                this.warningBanner.style.display = "block";
                this.warningList.innerHTML = unverified.map(item => `<li>${escapeHtml(String(item))}</li>`).join('');
            } else {
                this.warningBanner.style.display = "none";
            }

            // 3. Citations Chips Row
            const citations = data.citations || [];
            if (Array.isArray(citations) && citations.length > 0) {
                this.citationsSection.style.display = "block";
                this.citationsRow.innerHTML = citations.map(c => {
                    let label = "";
                    let url = null;
                    if (typeof c === "object" && c !== null) {
                        const circular = c.circular_no || c.title || "Circular";
                        const section = c.section ? ` (${c.section})` : "";
                        label = `${circular}${section}`;
                        url = c.url || null;
                    } else {
                        label = String(c);
                    }

                    if (url) {
                        return `<a class="rc-citation-chip" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                            <span>${escapeHtml(label)}</span>
                        </a>`;
                    } else {
                        return `<span class="rc-citation-chip rc-chip-static">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                            <span>${escapeHtml(label)}</span>
                        </span>`;
                    }
                }).join('');
            } else {
                this.citationsSection.style.display = "none";
            }

            // 4. Horizontal Effective Dates Timeline List
            const dates = data.effective_dates || [];
            if (Array.isArray(dates) && dates.length > 0) {
                this.timelineSection.style.display = "block";
                this.timelineTrack.innerHTML = dates.map(item => {
                    const { status, label, provision, dateStr } = determineDateStatus(item);
                    return `
                        <div class="rc-timeline-item status-${status}">
                            <div class="rc-timeline-header">
                                <span class="rc-timeline-badge rc-badge-${status}">${escapeHtml(label)}</span>
                                <span class="rc-timeline-date">${escapeHtml(dateStr || "N/A")}</span>
                            </div>
                            <div class="rc-timeline-body">${escapeHtml(provision || "Provision requirement")}</div>
                        </div>
                    `;
                }).join('');
            } else {
                this.timelineSection.style.display = "none";
            }

            // 5. Impacted Teams Tags with Tooltip
            const teams = data.impacted_teams || [];
            if (Array.isArray(teams) && teams.length > 0) {
                this.teamsSection.style.display = "block";
                this.teamsRow.innerHTML = teams.map(item => {
                    const { name, reason } = parseTeamItem(item);
                    return `
                        <div class="rc-team-tag" data-tooltip="${escapeHtml(reason)}">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                                <circle cx="9" cy="7" r="4"/>
                            </svg>
                            <span>${escapeHtml(name)}</span>
                            <div class="rc-tooltip">${escapeHtml(reason)}</div>
                        </div>
                    `;
                }).join('');
            } else {
                this.teamsSection.style.display = "none";
            }
        }
    }

    const RegulatoryCopilot = {
        mount(target, options = {}) {
            return new RegulatoryCopilotWidget(target, options);
        }
    };

    global.RegulatoryCopilot = RegulatoryCopilot;

    // Auto-mount on DOMContentLoaded
    document.addEventListener("DOMContentLoaded", () => {
        const autoTarget = document.querySelector("#regulatory-copilot-widget, #copilotWidget");
        if (autoTarget && !autoTarget.dataset.mounted) {
            autoTarget.dataset.mounted = "true";
            global.copilotInstance = RegulatoryCopilot.mount(autoTarget, { mode: "drawer" });
        }
    });

})(typeof window !== "undefined" ? window : this);
