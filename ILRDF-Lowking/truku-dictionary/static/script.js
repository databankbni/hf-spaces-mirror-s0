document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    
    // Split layout elements
    const splitLayout = document.getElementById('split-layout');
    const resultsList = document.getElementById('results-list');
    const searchStatsSummary = document.getElementById('search-stats-summary');
    const resultDetailCard = document.getElementById('result-detail-card');
    const emptyDetailState = document.getElementById('empty-detail-state');
    const loadingEl = document.getElementById('loading');
    const noResultsEl = document.getElementById('no-results');
    const exportCsvBtn = document.getElementById('exportCsvBtn');

    // API Key Settings
    const apiSettingsBtn = document.getElementById('apiSettingsBtn');
    if (apiSettingsBtn) {
        apiSettingsBtn.addEventListener('click', () => {
            const currentKey = localStorage.getItem('custom_gemini_api_key') || '';
            const newKey = prompt('系統已內建公用額度。若額度已用完，請填寫您個人的 Google Gemini API Key：\n（若要恢復使用系統預設額度，請清空並按確定）', currentKey);
            if (newKey !== null) {
                localStorage.setItem('custom_gemini_api_key', newKey.trim());
                if (newKey.trim()) {
                    alert('✅ 專屬 API Key 已儲存！接下來的標注將優先使用您的個人額度。');
                } else {
                    alert('🔄 已清除自訂 API Key，將恢復使用系統公用額度。');
                }
            }
        });
    }

    // Tab elements
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    // Stats elements
    const statsLoading = document.getElementById('stats-loading');
    const statsDashboard = document.getElementById('stats-dashboard');
    let statsLoaded = false;
    let letterChart = null;
    let wordChart = null;
    let prefixChart = null;
    let suffixChart = null;
    let corpusPieChart = null;

    let currentResults = [];
    let currentQuery = '';
    let currentSearchType = '';

    // --- Tab Switching Logic ---
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-tab');
            
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(targetId).classList.add('active');

            if (targetId === 'tab-stats' && !statsLoaded) {
                loadStats();
            }
        });
    });

    // --- Search Logic ---
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    exportCsvBtn.addEventListener('click', () => {
        if (!currentQuery) return;
        const searchType = document.querySelector('input[name="searchType"]:checked').value;
        const matchMode = document.querySelector('input[name="matchMode"]:checked').value;
        
        const corpusCheckboxes = document.querySelectorAll('input[name="corpus"]:checked');
        let corporaParams = '';
        if (corpusCheckboxes.length > 0) {
            const corpora = Array.from(corpusCheckboxes).map(cb => cb.value);
            corporaParams = '&' + corpora.map(c => `corpora[]=${encodeURIComponent(c)}`).join('&');
        }

        const exportUrl = `/api/export?q=${encodeURIComponent(currentQuery)}&type=${encodeURIComponent(searchType)}&match_mode=${encodeURIComponent(matchMode)}${corporaParams}`;
        window.location.href = exportUrl;
    });

    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        // Get options
        const searchType = document.querySelector('input[name="searchType"]:checked').value;
        const matchMode = document.querySelector('input[name="matchMode"]:checked').value;
        
        const corpusCheckboxes = document.querySelectorAll('input[name="corpus"]:checked');
        let corporaParams = '';
        if (corpusCheckboxes.length > 0) {
            const corpora = Array.from(corpusCheckboxes).map(cb => cb.value);
            corporaParams = '&' + corpora.map(c => `corpora[]=${encodeURIComponent(c)}`).join('&');
        }

        // Reset UI
        resultsList.innerHTML = '';
        searchStatsSummary.innerHTML = '';
        resultDetailCard.innerHTML = '';
        
        splitLayout.classList.add('hidden');
        searchStatsSummary.classList.add('hidden');
        resultDetailCard.innerHTML = '';
        emptyDetailState.style.display = 'flex';
        noResultsEl.classList.add('hidden');
        loadingEl.classList.remove('hidden');
        exportCsvBtn.classList.add('hidden');

        try {
            const url = `/api/search?q=${encodeURIComponent(query)}&type=${encodeURIComponent(searchType)}&match_mode=${encodeURIComponent(matchMode)}${corporaParams}`;
            const response = await fetch(url);
            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            loadingEl.classList.add('hidden');
            
            if (data.results.length === 0) {
                noResultsEl.classList.remove('hidden');
            } else {
                currentResults = data.results;
                currentQuery = query;
                currentSearchType = searchType;
                
                splitLayout.classList.remove('hidden');
                exportCsvBtn.classList.remove('hidden');
                renderSearchSummary(data, query, searchType, matchMode);
                renderResultsList(data.results, query, searchType);
            }
        } catch (error) {
            console.error('Error fetching data:', error);
            loadingEl.classList.add('hidden');
            noResultsEl.classList.remove('hidden');
            noResultsEl.innerHTML = `<p style="color: #ef4444;">發生錯誤，無法取得資料。</p>`;
        }
    }

    function renderSearchSummary(data, query, searchType, matchMode) {
        searchStatsSummary.innerHTML = '';
        searchStatsSummary.classList.remove('hidden');
        
        let collocationsHtml = '';
        if (data.collocations && data.collocations.length > 0) {
            const badgesHtml = data.collocations.map(word => 
                `<span class="collocation-badge" data-word="${word}">${word}</span>`
            ).join('');
            
            collocationsHtml = `
                <div style="margin-top: 1rem;">
                    <span style="color: var(--text-muted); margin-right: 0.5rem;">常用共現關聯詞:</span>
                    <div class="collocations-container">${badgesHtml}</div>
                </div>
            `;
        }
        
        let positionsHtml = '';
        if (data.positions) {
            const total = data.positions.initial + data.positions.medial + data.positions.final;
            if (total > 0) {
                const pInit = Math.round((data.positions.initial / total) * 100);
                const pMed = Math.round((data.positions.medial / total) * 100);
                const pFin = Math.round((data.positions.final / total) * 100);
                
                positionsHtml = `
                    <div class="stats-grid" id="position-filters">
                        <div class="stat-item position-btn" data-pos="initial" style="cursor: pointer; transition: 0.2s;">
                            <div class="label">句首 (Initial)</div>
                            <div class="value">${data.positions.initial} 次</div>
                            <div class="pct">${pInit}%</div>
                        </div>
                        <div class="stat-item position-btn" data-pos="medial" style="cursor: pointer; transition: 0.2s;">
                            <div class="label">句中 (Medial)</div>
                            <div class="value">${data.positions.medial} 次</div>
                            <div class="pct">${pMed}%</div>
                        </div>
                        <div class="stat-item position-btn" data-pos="final" style="cursor: pointer; transition: 0.2s;">
                            <div class="label">句尾 (Final)</div>
                            <div class="value">${data.positions.final} 次</div>
                            <div class="pct">${pFin}%</div>
                        </div>
                    </div>
                `;
            }
        }

        let summaryText = '';
        if (matchMode === 'partial') {
            summaryText = `<div style="line-height: 1.8;">💡 關鍵字 <span class="highlight-count">"${query}"</span> 在所選語料中部分搜尋共出現 <span class="highlight-count">${data.total_occurrences}</span> 次，其中精準搜尋共出現 <span class="highlight-count">${data.exact_occurrences}</span> 次。<br>`;
            if (data.corpus_breakdown) {
                // First show all corpus counts
                for (const [corpus, counts] of Object.entries(data.corpus_breakdown)) {
                    summaryText += `💡 其中在 "${corpus}" 中部分搜尋共出現 <span class="highlight-count">${counts.total}</span> 次。<br>`;
                }
                // Then show subcategories for specific corpora
                for (const [corpus, counts] of Object.entries(data.corpus_breakdown)) {
                    if (['族語E樂園', '語推組織語料'].includes(corpus) && counts.subcategories && Object.keys(counts.subcategories).length > 0) {
                        const subBtnsHtml = Object.entries(counts.subcategories).map(([subcat, count]) => {
                            return `<div class="stat-item subcat-btn" data-subcat="${subcat}" style="cursor: pointer; transition: 0.2s; background: rgba(251, 146, 60, 0.1); border: 1px solid rgba(251, 146, 60, 0.3); padding: 0.5rem; border-radius: 6px; display: inline-block; min-width: 80px; text-align: center;">
                                <div style="color: #fb923c; font-weight: bold; font-size: 0.9rem;">${subcat}</div>
                                <div style="color: #e2e8f0; font-size: 0.85rem;">${count} 筆</div>
                            </div>`;
                        }).join('');
                        summaryText += `<div style="margin-top: 0.5rem; margin-bottom: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem;" id="subcat-filters">${subBtnsHtml}</div>`;
                    }
                }
            }
            summaryText += `</div>`;
        } else {
            summaryText = `<div style="line-height: 1.8;">💡 關鍵字 <span class="highlight-count">"${query}"</span> 在所選語料中共精準出現了 <span class="highlight-count">${data.total_occurrences}</span> 次。<br>`;
            if (data.corpus_breakdown) {
                // First show all corpus counts
                for (const [corpus, counts] of Object.entries(data.corpus_breakdown)) {
                    summaryText += `💡 其中在 "${corpus}" 中共精準出現了 <span class="highlight-count">${counts.exact}</span> 次。<br>`;
                }
                // Then show subcategories for specific corpora
                for (const [corpus, counts] of Object.entries(data.corpus_breakdown)) {
                    if (['族語E樂園', '語推組織語料'].includes(corpus) && counts.subcategories && Object.keys(counts.subcategories).length > 0) {
                        const subBtnsHtml = Object.entries(counts.subcategories).map(([subcat, count]) => {
                            return `<div class="stat-item subcat-btn" data-subcat="${subcat}" style="cursor: pointer; transition: 0.2s; background: rgba(251, 146, 60, 0.1); border: 1px solid rgba(251, 146, 60, 0.3); padding: 0.5rem; border-radius: 6px; display: inline-block; min-width: 80px; text-align: center;">
                                <div style="color: #fb923c; font-weight: bold; font-size: 0.9rem;">${subcat}</div>
                                <div style="color: #e2e8f0; font-size: 0.85rem;">${count} 筆</div>
                            </div>`;
                        }).join('');
                        summaryText += `<div style="margin-top: 0.5rem; margin-bottom: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem;" id="subcat-filters">${subBtnsHtml}</div>`;
                    }
                }
            }
            summaryText += `</div>`;
        }
        
        let ngramsHtml = '';
        if (data.ngrams && (data.ngrams.bigrams?.length > 0 || data.ngrams.trigrams?.length > 0)) {
            const renderNgram = (ng) => `<div style="background: rgba(0,0,0,0.3); padding: 0.3rem 0.6rem; border-radius: 4px; display: inline-flex; align-items: center; gap: 0.5rem; margin: 0.2rem;"><span style="color: #e2e8f0;">${ng.ngram}</span><span style="color: #60a5fa; font-size: 0.85em;">${ng.count}次</span></div>`;
            
            const bigramsHtml = (data.ngrams.bigrams || []).map(renderNgram).join('');
            const trigramsHtml = (data.ngrams.trigrams || []).map(renderNgram).join('');
            
            ngramsHtml = `
                <div style="margin-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 1rem;">
                    <div style="color: var(--text-muted); margin-bottom: 0.5rem; font-weight: bold;">連詞分析 (N-grams):</div>
                    ${bigramsHtml ? `<div style="margin-bottom: 0.5rem;"><span style="color: #94a3b8; font-size: 0.9em; width: 60px; display: inline-block;">雙詞:</span> ${bigramsHtml}</div>` : ''}
                    ${trigramsHtml ? `<div><span style="color: #94a3b8; font-size: 0.9em; width: 60px; display: inline-block;">三詞:</span> ${trigramsHtml}</div>` : ''}
                </div>
            `;
        }

        let morphHtml = '';
        if (data.morphology) {
            const familyBtns = data.morphology.family.map(fw => 
                `<button onclick="document.getElementById('searchInput').value='${fw}'; document.getElementById('searchBtn').click();" style="background: rgba(99,102,241,0.2); border: 1px solid rgba(99,102,241,0.5); color: #818cf8; padding: 0.3rem 0.6rem; border-radius: 4px; cursor: pointer; transition: all 0.2s; margin: 0.2rem;" onmouseover="this.style.background='rgba(99,102,241,0.4)'" onmouseout="this.style.background='rgba(99,102,241,0.2)'">${fw}</button>`
            ).join('');
            
            morphHtml = `
                <div style="margin-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 1rem;">
                    <div style="color: #a78bfa; margin-bottom: 0.5rem; font-weight: bold;">✨ 構詞學分析 (Morphology):</div>
                    <div style="margin-bottom: 0.5rem;"><span style="color: #94a3b8; font-size: 0.9em; width: 80px; display: inline-block;">推測詞根:</span> <span style="color: #e2e8f0; font-weight: bold;">${data.morphology.root}</span></div>
                    <div><span style="color: #94a3b8; font-size: 0.9em; width: 80px; display: inline-block; vertical-align: top;">家族詞彙:</span> <div style="display: inline-block; width: calc(100% - 85px);">${familyBtns}</div></div>
                </div>
            `;
        }

        searchStatsSummary.innerHTML = `
            <p>${summaryText}</p>
            ${morphHtml}
            ${collocationsHtml}
            ${ngramsHtml}
            ${positionsHtml}
        `;

        const badges = searchStatsSummary.querySelectorAll('.collocation-badge');
        badges.forEach(badge => {
            badge.addEventListener('click', () => {
                const word = badge.getAttribute('data-word');
                searchInput.value = word;
                document.querySelector('input[name="searchType"][value="truku"]').checked = true;
                performSearch();
            });
        });

        // Position Filtering
        const posBtns = searchStatsSummary.querySelectorAll('.position-btn');
        let activePos = null;
        
        posBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const pos = btn.getAttribute('data-pos');
                if (activePos === pos) {
                    // Toggle off
                    activePos = null;
                    posBtns.forEach(b => {
                        b.style.background = 'rgba(0,0,0,0.2)';
                        b.style.border = 'none';
                    });
                    renderResultsList(data.results, query, searchType);
                } else {
                    // Toggle on
                    activePos = pos;
                    posBtns.forEach(b => {
                        b.style.background = 'rgba(0,0,0,0.2)';
                        b.style.border = 'none';
                    });
                    btn.style.background = 'rgba(59, 130, 246, 0.2)';
                    btn.style.border = '1px solid rgba(59, 130, 246, 0.5)';
                    
                    const filtered = data.results.filter(r => r.positions && r.positions.includes(pos));
                    renderResultsList(filtered, query, searchType);
                }
            });
        });

        // Subcategory Filtering
        const subcatBtns = searchStatsSummary.querySelectorAll('.subcat-btn');
        let activeSubcat = null;
        
        subcatBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const subcat = btn.getAttribute('data-subcat');
                if (activeSubcat === subcat) {
                    activeSubcat = null;
                    subcatBtns.forEach(b => {
                        b.style.background = 'rgba(251, 146, 60, 0.1)';
                        b.style.border = '1px solid rgba(251, 146, 60, 0.3)';
                    });
                    renderResultsList(data.results, query, searchType);
                } else {
                    activeSubcat = subcat;
                    subcatBtns.forEach(b => {
                        b.style.background = 'rgba(0,0,0,0.2)';
                        b.style.border = '1px solid transparent';
                    });
                    btn.style.background = 'rgba(251, 146, 60, 0.3)';
                    btn.style.border = '1px solid rgba(251, 146, 60, 0.8)';
                    
                    const filtered = data.results.filter(r => r.detailed_source && r.detailed_source.includes(subcat));
                    renderResultsList(filtered, query, searchType);
                }
            });
        });
    }

    function renderResultsList(results, query, searchType) {
        resultsList.innerHTML = '';
        
        let displayResults = results;
        let isTruncated = false;
        if (results.length > 200) {
            displayResults = results.slice(0, 200);
            isTruncated = true;
        }
        
        if (displayResults.length === 0) {
            resultsList.innerHTML = '<div style="padding: 1rem; color: #94a3b8; text-align: center;">沒有符合此條件的結果。</div>';
            return;
        }
        
        displayResults.forEach((item, index) => {
            const li = document.createElement('div');
            li.className = `list-item ${index === 0 ? 'active' : ''}`;
            
            let displayTruku = item.truku_sentence || '';
            let displayChinese = item.chinese_translation || '';
            const highlightRegex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
            
            if (searchType === 'truku' || searchType === 'source') {
                displayTruku = displayTruku.replace(highlightRegex, '<span style="color: var(--highlight-bg); font-weight: bold;">$1</span>');
            } else if (searchType === 'chinese') {
                displayChinese = displayChinese.replace(highlightRegex, '<span style="color: var(--highlight-bg); font-weight: bold;">$1</span>');
            }

            let badgeHtml = '';
            if (item.is_exact !== undefined) {
                badgeHtml = item.is_exact 
                    ? '<span class="list-item-badge badge-exact">精準</span>'
                    : '<span class="list-item-badge badge-partial">部分</span>';
            }
            
            let corpusBadge = '';
            let subcatBadge = '';
            if (item.corpus_source === '族語辭典') {
                corpusBadge = '<span class="list-item-badge badge-corpus-dict">辭典</span>';
            } else if (item.corpus_source === '族語E樂園') {
                corpusBadge = '<span class="list-item-badge badge-corpus-klokah">E樂園</span>';
                if (item.detailed_source && item.detailed_source.trim() !== '') {
                    subcatBadge = `<span class="list-item-badge badge-corpus-subcat">${item.detailed_source.replace(/^族語E樂園 - /, '')}</span>`;
                }
            } else if (item.corpus_source === '族語文學') {
                corpusBadge = '<span class="list-item-badge badge-corpus-lit">文學</span>';
            } else if (item.corpus_source === '語推組織語料') {
                corpusBadge = '<span class="list-item-badge badge-corpus-org">語推</span>';
                if (item.detailed_source && item.detailed_source.trim() !== '') {
                    subcatBadge = `<span class="list-item-badge badge-corpus-subcat">${item.detailed_source}</span>`;
                }
            } else if (item.corpus_source === '族語資料庫語料') {
                corpusBadge = '<span class="list-item-badge badge-corpus-db">資料庫</span>';
            } else if (item.corpus_source) {
                corpusBadge = `<span class="list-item-badge badge-corpus-dict">${item.corpus_source}</span>`;
            }

            li.innerHTML = `
                <div class="list-item-truku">${corpusBadge} ${subcatBadge} ${displayTruku} ${badgeHtml}</div>
                <div class="list-item-chinese">${displayChinese}</div>
            `;
            
            li.addEventListener('click', () => {
                document.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                li.classList.add('active');
                renderDetailCard(item);
            });
            
            resultsList.appendChild(li);
        });

        if (isTruncated) {
            const truncRow = document.createElement('div');
            truncRow.style.padding = '1rem';
            truncRow.style.textAlign = 'center';
            truncRow.style.color = '#94a3b8';
            truncRow.style.fontSize = '0.9rem';
            truncRow.innerHTML = `已隱藏其餘 ${results.length - 200} 筆結果。請縮小搜尋範圍或點擊「匯出 CSV」檢視全部資料。`;
            resultsList.appendChild(truncRow);
        }

        if (displayResults.length > 0) {
            renderDetailCard(displayResults[0]);
        }
    }

    function renderDetailCard(item) {
        emptyDetailState.style.display = 'none';
        resultDetailCard.classList.remove('hidden');
        
        let displayTruku = item.truku_sentence || '';
        let displayChinese = item.chinese_translation || '';
        let displaySource = item.source_word || '';
        let kwicText = item.kwic_sentence || '';

        const highlightRegex = new RegExp(`(${escapeRegExp(currentQuery)})`, 'gi');
        
        if (currentSearchType === 'truku') {
            kwicText = kwicText.replace(highlightRegex, '<span class="keyword-highlight">$1</span>');
            displayTruku = displayTruku.replace(highlightRegex, '<span style="color: var(--highlight-bg); font-weight: bold;">$1</span>');
        } else if (currentSearchType === 'chinese') {
            displayChinese = displayChinese.replace(highlightRegex, '<span style="color: var(--highlight-bg); font-weight: bold;">$1</span>');
        } else if (currentSearchType === 'source') {
            displaySource = displaySource.replace(highlightRegex, '<span style="color: var(--highlight-bg); font-weight: bold;">$1</span>');
            displayTruku = displayTruku.replace(highlightRegex, '<span style="color: var(--highlight-bg); font-weight: bold;">$1</span>');
        }

        const kwicBlock = currentSearchType === 'truku' 
            ? `<div class="kwic-text">搭配詞： ${kwicText}</div>`
            : `<div class="truku-text">${displayTruku}</div>`;

        resultDetailCard.innerHTML = `
            <div class="card">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <h2>${displaySource || '詳細資訊'}</h2>
                        <span class="badge ${item.is_exact ? 'badge-exact' : 'badge-partial'}">
                            ${item.is_exact ? '精準匹配' : '部分匹配'}
                        </span>
                    </div>
                    <a href="#" onclick="openReportModal('sentence_error', ${item.id}, \`${(item.truku_sentence || item.source_word || '').replace(/`/g, '')}\`); return false;" 
                       class="report-btn" style="padding: 0.3rem 0.6rem; font-size: 0.8rem; background: rgba(245, 158, 11, 0.1); color: #f59e0b; border-color: rgba(245, 158, 11, 0.3);">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                        回報此句
                    </a>
                </div>
                <div class="card-body">
                    ${kwicBlock}
                    ${currentSearchType === 'truku' ? `<div class="truku-text" style="font-size: 0.9em; color: var(--text-muted);">完整例句： ${displayTruku}</div>` : ''}
                    <div class="chinese-text">${displayChinese}</div>
                    ${item.full_explanation ? `<div class="explanation">${item.full_explanation.replace(/;/g, '<br>')}</div>` : ''}
                    
                    <!-- IGT Annotation Trigger -->
                    <div style="margin-top: 1.2rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.08); display:flex; gap:0.6rem; flex-wrap:wrap; align-items:center;">
                        <button 
                            onclick="triggerGlosser(this, \`${(item.truku_sentence || '').replace(/`/g, "'")}\`, \`${(item.chinese_translation || '').replace(/`/g, "'")}\`)"
                            style="background: rgba(139,92,246,0.15); color: #a78bfa; border: 1px solid rgba(139,92,246,0.4); padding: 0.35rem 0.9rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; transition: all 0.2s; display: inline-flex; align-items: center; gap: 0.4rem;"
                            onmouseover="this.style.background='rgba(139,92,246,0.3)'"
                            onmouseout="this.style.background='rgba(139,92,246,0.15)'"
                        >
                            🏷️ 快速標注 (IGT)
                        </button>
                        <button
                            onclick="sendToGlosser(\`${(item.truku_sentence || '').replace(/`/g, "'")}\`, \`${(item.chinese_translation || '').replace(/`/g, "'")}\`)"
                            style="background: rgba(52,211,153,0.12); color: #34d399; border: 1px solid rgba(52,211,153,0.3); padding: 0.35rem 0.9rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; transition: all 0.2s; display: inline-flex; align-items: center; gap: 0.4rem;"
                            onmouseover="this.style.background='rgba(52,211,153,0.25)'"
                            onmouseout="this.style.background='rgba(52,211,153,0.12)'"
                        >
                            ↗️ 送往標注頁籤
                        </button>
                    </div>
                    <div class="igt-output-area" style="display:none; margin-top: 1rem;"></div>
                </div>
            </div>
        `;
    }

    function escapeRegExp(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // --- IGT Glosser Integration ---
    // Calls truku-glosser backend (port 8000) and renders 4-line IGT format
    // --- Stats Logic ---
    async function loadStats() {
        statsLoading.classList.remove('hidden');
        
        try {
            const response = await fetch('/api/stats');
            if (!response.ok) throw new Error('Network response was not ok');
            const data = await response.json();
            
            statsLoading.classList.add('hidden');
            statsDashboard.classList.remove('hidden');
            
            document.getElementById('stat-entries').innerText = data.total_entries.toLocaleString();
            document.getElementById('stat-sentences').innerText = data.total_sentences.toLocaleString();
            document.getElementById('stat-avg-len').innerText = data.avg_sentence_length.toLocaleString();

            initSubTabs();
            renderCharts(data);
            statsLoaded = true;
        } catch (error) {
            console.error('Error fetching stats:', error);
            statsLoading.innerHTML = `<p style="color: #ef4444;">載入統計資料失敗。</p>`;
        }
    }

    function initSubTabs() {
        const subTabBtns = document.querySelectorAll('.sub-tab-btn');
        const subTabContents = document.querySelectorAll('.sub-tab-content');
        
        subTabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                subTabBtns.forEach(b => b.classList.remove('active'));
                subTabContents.forEach(c => c.classList.add('hidden'));
                
                btn.classList.add('active');
                document.getElementById(btn.dataset.subtab).classList.remove('hidden');
                
                // Force charts to resize when their container becomes visible
                setTimeout(() => {
                    if (wordChart) wordChart.resize();
                    if (letterChart) letterChart.resize();
                    if (prefixChart) prefixChart.resize();
                    if (suffixChart) suffixChart.resize();
                }, 10);
            });
        });
    }

    function renderCharts(data) {
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';
        
        if (typeof ChartDataLabels !== 'undefined') {
            Chart.register(ChartDataLabels);
        }

        // 1. Corpus Pie Chart
        const pieCtx = document.getElementById('corpusPieChart').getContext('2d');
        const corpusKeys = Object.keys(data.corpus_distribution);
        const corpusValues = corpusKeys.map(k => data.corpus_distribution[k]);
        const corpusColors = corpusKeys.map(k => {
            if (k === '族語辭典') return '#60a5fa';
            if (k === '族語E樂園') return '#a855f7';
            if (k === '族語文學') return '#10b981';
            return '#f59e0b';
        });

        if (corpusPieChart) corpusPieChart.destroy();
        corpusPieChart = new Chart(pieCtx, {
            type: 'doughnut',
            data: {
                labels: corpusKeys,
                datasets: [{
                    data: corpusValues,
                    backgroundColor: corpusColors,
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'bottom', labels: { color: '#e2e8f0' } },
                    datalabels: {
                        color: '#fff',
                        font: { weight: 'bold' },
                        formatter: (value, ctx) => {
                            let sum = 0;
                            let dataArr = ctx.chart.data.datasets[0].data;
                            dataArr.map(data => { sum += data; });
                            let percentage = (value*100 / sum).toFixed(1)+"%";
                            return percentage;
                        }
                    }
                }
            }
        });

        // 2. Letter Chart
        const letterCtx = document.getElementById('letterChart').getContext('2d');
        const letterKeys = Object.keys(data.first_letters).sort();
        const letterValues = letterKeys.map(k => data.first_letters[k]);
        
        const bgColors = letterKeys.map((_, i) => `hsla(${i * (360/letterKeys.length)}, 70%, 60%, 0.6)`);
        const borderColors = letterKeys.map((_, i) => `hsla(${i * (360/letterKeys.length)}, 70%, 60%, 1)`);

        if (letterChart) letterChart.destroy();
        letterChart = new Chart(letterCtx, {
            type: 'bar',
            data: {
                labels: letterKeys.map(k => k.toUpperCase()),
                datasets: [{
                    label: '詞條數量',
                    data: letterValues,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1
                }]
            },
            options: { 
                responsive: true, 
                plugins: { 
                    legend: { display: false },
                    datalabels: {
                        color: '#e2e8f0',
                        anchor: 'end',
                        align: 'top',
                        formatter: Math.round,
                        font: { weight: 'bold' }
                    }
                } 
            }
        });

        // Prefix Chart
        if (data.prefixes) {
            const preCtx = document.getElementById('prefixChart').getContext('2d');
            const preKeys = Object.keys(data.prefixes);
            const preVals = preKeys.map(k => data.prefixes[k]);
            if (prefixChart) prefixChart.destroy();
            prefixChart = new Chart(preCtx, {
                type: 'bar',
                data: {
                    labels: preKeys,
                    datasets: [{
                        data: preVals,
                        backgroundColor: 'rgba(236, 72, 153, 0.6)',
                        borderColor: 'rgba(236, 72, 153, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false }, datalabels: { color: '#e2e8f0', anchor: 'end', align: 'top', font: { weight: 'bold' } } }
                }
            });
        }

        // Suffix Chart
        if (data.suffixes) {
            const sufCtx = document.getElementById('suffixChart').getContext('2d');
            const sufKeys = Object.keys(data.suffixes);
            const sufVals = sufKeys.map(k => data.suffixes[k]);
            if (suffixChart) suffixChart.destroy();
            suffixChart = new Chart(sufCtx, {
                type: 'bar',
                data: {
                    labels: sufKeys,
                    datasets: [{
                        data: sufVals,
                        backgroundColor: 'rgba(16, 185, 129, 0.6)',
                        borderColor: 'rgba(16, 185, 129, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false }, datalabels: { color: '#e2e8f0', anchor: 'end', align: 'top', font: { weight: 'bold' } } }
                }
            });
        }

        // 3. Top Words
        const top50 = data.top_words;
        const topWordsKeys = top50.map(item => item.word);
        const topWordsValues = top50.map(item => item.count);

        if (wordChart) wordChart.destroy();
        const wordCtx = document.getElementById('wordChart').getContext('2d');
        wordChart = new Chart(wordCtx, {
            type: 'bar',
            data: {
                labels: topWordsKeys,
                datasets: [{
                    label: '出現次數',
                    data: topWordsValues,
                    backgroundColor: '#3b82f6',
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    datalabels: {
                        color: '#e2e8f0',
                        anchor: 'end',
                        align: 'right',
                        formatter: Math.round,
                        font: { weight: 'bold', size: 10 }
                    }
                },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.05)' }, max: Math.max(...topWordsValues) * 1.15 },
                    y: { grid: { display: false } }
                }
            }
        });

        // Populate Left List
        const listContainer = document.getElementById('stats-word-list');
        listContainer.innerHTML = top50.map(item => `
            <div class="stats-list-row">
                <div class="col-word">
                    ${item.word}
                    ${item.translation ? `<span style="color:#94a3b8; font-size:0.85em; margin-left:0.5rem;">(${item.translation})</span>` : ''}
                </div>
                <div class="col-count">${item.count.toLocaleString()}</div>
            </div>
        `).join('');
        
        // Populate N-grams
        const bigramsContainer = document.getElementById('stats-bigrams');
        bigramsContainer.innerHTML = Object.entries(data.top_bigrams).sort((a,b)=>b[1]-a[1]).map(item => `
            <div class="ngram-item">
                <span class="ngram-text">${item[0]}</span>
                <span class="ngram-count">${item[1].toLocaleString()}次</span>
            </div>
        `).join('');
        
        const trigramsContainer = document.getElementById('stats-trigrams');
        trigramsContainer.innerHTML = Object.entries(data.top_trigrams).sort((a,b)=>b[1]-a[1]).map(item => `
            <div class="ngram-item">
                <span class="ngram-text">${item[0]}</span>
                <span class="ngram-count">${item[1].toLocaleString()}次</span>
            </div>
        `).join('');

        // Populate Corpus Compare Table
        if (data.top_words_by_corpus) {
            const tableBody = document.querySelector('#corpus-compare-table tbody');
            const dictTop = data.top_words_by_corpus['族語辭典'] || [];
            const klokahTop = data.top_words_by_corpus['族語E樂園'] || [];
            const litTop = data.top_words_by_corpus['族語文學'] || [];
            
            let tableHtml = '';
            for (let i = 0; i < 50; i++) {
                const dictItem = dictTop[i] || {word: '-', count: 0, translation: ''};
                const klokahItem = klokahTop[i] || {word: '-', count: 0, translation: ''};
                const litItem = litTop[i] || {word: '-', count: 0, translation: ''};
                
                tableHtml += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.05)'" onmouseout="this.style.background='transparent'">
                        <td style="padding: 0.75rem 1rem; color: #94a3b8;">${i + 1}</td>
                        <td style="padding: 0.75rem 1rem;">
                            <span style="color: #e2e8f0; font-weight: 500;">${dictItem.word}</span>
                            ${dictItem.word !== '-' ? `<span style="color: #60a5fa; margin-left: 0.5rem; font-size: 0.85em;">(${dictItem.count})</span><span style="color: rgba(255,255,255,0.4); margin-left: 0.3rem; font-size: 0.8em;">${dictItem.percentage}%</span>` : ''}
                            ${dictItem.translation ? `<div style="color: #64748b; font-size: 0.8em; margin-top: 0.2rem;">${dictItem.translation}</div>` : ''}
                        </td>
                        <td style="padding: 0.75rem 1rem;">
                            <span style="color: #e2e8f0; font-weight: 500;">${klokahItem.word}</span>
                            ${klokahItem.word !== '-' ? `<span style="color: #fde047; margin-left: 0.5rem; font-size: 0.85em;">(${klokahItem.count})</span><span style="color: rgba(255,255,255,0.4); margin-left: 0.3rem; font-size: 0.8em;">${klokahItem.percentage}%</span>` : ''}
                            ${klokahItem.translation ? `<div style="color: #64748b; font-size: 0.8em; margin-top: 0.2rem;">${klokahItem.translation}</div>` : ''}
                        </td>
                        <td style="padding: 0.75rem 1rem;">
                            <span style="color: #e2e8f0; font-weight: 500;">${litItem.word}</span>
                            ${litItem.word !== '-' ? `<span style="color: #10b981; margin-left: 0.5rem; font-size: 0.85em;">(${litItem.count})</span><span style="color: rgba(255,255,255,0.4); margin-left: 0.3rem; font-size: 0.8em;">${litItem.percentage}%</span>` : ''}
                            ${litItem.translation ? `<div style="color: #64748b; font-size: 0.8em; margin-top: 0.2rem;">${litItem.translation}</div>` : ''}
                        </td>
                    </tr>
                `;
            }
            if (tableBody) tableBody.innerHTML = tableHtml;
        }
    }
});

window.openReportModal = function(type, id = null, sentence = '') {
    const modal = document.getElementById('reportModal');
    const typeSelect = document.getElementById('reportType');
    const sentenceGroup = document.getElementById('reportSentenceGroup');
    const sentenceArea = document.getElementById('reportSentence');
    const idInput = document.getElementById('reportSentenceId');
    
    typeSelect.value = type;
    document.getElementById('reportDescription').value = '';
    document.getElementById('reportMessage').innerHTML = '';
    
    if (type === 'sentence_error' && id) {
        sentenceGroup.style.display = 'block';
        sentenceArea.value = sentence;
        idInput.value = id;
    } else {
        sentenceGroup.style.display = 'none';
        sentenceArea.value = '';
        idInput.value = '';
    }
    
    modal.classList.remove('hidden');
}

window.closeReportModal = function() {
    document.getElementById('reportModal').classList.add('hidden');
}

window.submitReport = async function() {
    const type = document.getElementById('reportType').value;
    const description = document.getElementById('reportDescription').value;
    const email = document.getElementById('reportEmail').value;
    const sentenceId = document.getElementById('reportSentenceId').value;
    const sentence = document.getElementById('reportSentence').value;
    
    if (!description.trim()) {
        alert('請填寫詳細說明！');
        return;
    }
    
    const btn = document.getElementById('submitReportBtn');
    const msg = document.getElementById('reportMessage');
    btn.disabled = true;
    btn.innerText = '傳送中...';
    msg.innerHTML = '';
    
    try {
        const res = await fetch('/api/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, description, email, sentenceId, sentence })
        });
        const data = await res.json();
        
        if (res.ok) {
            msg.style.color = '#10b981';
            msg.innerHTML = '✅ 回報已成功送出給 lowking@ilrdf.org.tw！謝謝您！';
            setTimeout(() => closeReportModal(), 2000);
        } else {
            throw new Error(data.error || 'Server error');
        }
    } catch (error) {
        msg.style.color = '#ef4444';
        msg.innerHTML = '❌ 傳送失敗，請稍後再試。';
    } finally {
        btn.disabled = false;
        btn.innerText = '送出回報';
    }
}

// Global variables to store current analyzed words for export
let currentAiWord1 = '';
let currentAiWord2 = '';

// =========================================================
// 🏷️  IGT Glosser Integration — triggerGlosser()
// Calls truku-glosser backend on port 8000, renders 4-line IGT
// =========================================================
window.triggerGlosser = async function(btn, trukuSentence, chineseTranslation) {
    const outputArea = btn.closest('.card-body').querySelector('.igt-output-area');
    
    // Toggle: if already showing, hide it
    if (outputArea.style.display !== 'none' && outputArea.innerHTML !== '') {
        outputArea.style.display = 'none';
        btn.innerHTML = '🏷️ 語言學標注 (IGT)';
        return;
    }

    btn.innerHTML = '⏳ 分析中...';
    btn.disabled = true;
    outputArea.style.display = 'block';
    outputArea.innerHTML = `<div style="color:#a78bfa; font-size:0.85rem; padding:0.5rem 0;">正在呼叫語言學標注引擎（Port 8000）...</div>`;

    try {
        const response = await fetch('/api/parse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ truku_sentence: trukuSentence, chinese_translation: chineseTranslation })
        });

        if (!response.ok) {
            const err = await response.text();
            throw new Error(err);
        }

        const data = await response.json();
        const sentences = data.sentences || [];

        if (sentences.length === 0) {
            outputArea.innerHTML = `<div style="color:#fca5a5;">標注引擎未回傳結果。</div>`;
            return;
        }

        // Build 4-line IGT HTML
        let igtHtml = `<div class="igt-container">`;

        sentences.forEach((sentObj, sIdx) => {
            const words = sentObj.words || [];
            const translation = sentObj.translation || chineseTranslation || '';

            // Build the raw sentence (Line 1) from words
            const originalLine = words.map(w => w.raw).join('  ');

            // Word columns for lines 2 & 3
            const wordColsHtml = words.map((w, i) => {
                const isLow = w.confidence === 'low';
                return `
                    <div class="igt-word-col ${isLow ? 'igt-low-conf' : ''}" data-idx="${sIdx}-${i}" data-raw="${(w.raw||'').replace(/"/g,"'")}">
                        <div class="igt-l2" contenteditable="true" title="詞素切分（可編輯）">${(w.morph||w.raw).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
                        <div class="igt-l3" contenteditable="true" title="語法標記（可編輯）">${(w.gloss||'').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
                    </div>`;
            }).join('');

            igtHtml += `
                <div class="igt-block" data-sidx="${sIdx}">
                    <div class="igt-l1">${originalLine}</div>
                    <div class="igt-words-row">${wordColsHtml}</div>
                    <div class="igt-l4">${translation}</div>
                    <div class="igt-actions">
                        <button class="igt-save-btn" onclick="igtSave(this, ${sIdx})">💾 儲存至記憶庫</button>
                        <button class="igt-csv-btn" onclick="igtDownloadCsv(this)">📥 CSV</button>
                        <button class="igt-word-btn" onclick="igtDownloadWord(this, ${sIdx})">📝 Word</button>
                        <button class="igt-csv-btn" style="background:#0ea5e9;color:white;border-color:#0284c7;" onclick="importToDictSentence(this)">📖 匯入為主辭典例句</button>
                        <span class="igt-save-msg" style="color:#4ade80; font-size:0.8rem; display:none;">✅ 已儲存！</span>
                    </div>
                </div>`;
        });

        igtHtml += `</div>`;
        outputArea.innerHTML = igtHtml;

        // Store raw data on the container for download functions
        outputArea._glosserData = sentences;

        btn.innerHTML = '🏷️ 收起標注';
    } catch (e) {
        outputArea.innerHTML = `<div style="color:#fca5a5; font-size:0.85rem;">❌ 標注失敗：${e.message}<br><small>請確認 truku-glosser 後端（Port 8000）已啟動。</small></div>`;
        btn.innerHTML = '🏷️ 語言學標注 (IGT)';
    } finally {
        btn.disabled = false;
    }
};

window.igtSave = async function(btn, sIdx) {
    if (!confirm("確定要將這些單字校正儲存至記憶庫嗎？\n這將做為未來 AI 自動標注的黃金標準！")) return;
    const block = btn.closest('.igt-block');
    const words = Array.from(block.querySelectorAll('.igt-word-col')).map(col => ({
        raw: col.dataset.raw,
        morph: col.querySelector('.igt-l2').innerText.trim(),
        gloss: col.querySelector('.igt-l3').innerText.trim()
    }));
    const msgEl = btn.nextElementSibling.nextElementSibling;
    try {
        const res = await fetch('/api/save_correct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ words })
        });
        if (res.ok) {
            msgEl.style.display = 'inline';
            setTimeout(() => { msgEl.style.display = 'none'; }, 3000);
            alert("✅ 儲存成功！");
            
            try {
                const trukuSentence = block.querySelector('.igt-l1').innerText.trim();
                const chineseTranslation = block.querySelector('.igt-l4').innerText.trim();
                
                const checkRes = await fetch('/api/dictionary/check_sentence', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ truku_sentence: trukuSentence })
                });
                if (checkRes.ok) {
                    const checkData = await checkRes.json();
                    if (!checkData.exists) {
                        if (confirm(`發現這整句例句目前不在主辭典中：\n\n${trukuSentence}\n\n請問要順便將它新增到主辭典嗎？（邊標注、邊擴充）`)) {
                            await fetch('/api/dictionary/add_sentence', {
                                method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ truku_sentence: trukuSentence, chinese_translation: chineseTranslation })
                            });
                            alert("✅ 例句擴充成功！");
                        }
                    }
                }
            } catch(e) { console.error(e); }
        }
    } catch(e) { alert('儲存失敗，請確認標注後端已開啟。'); }
};

window.igtDownloadCsv = function(btn) {
    const outputArea = btn.closest('.igt-output-area');
    const sentences = outputArea._glosserData || [];
    let csv = '\uFEFF句子編號,行一(原文),行二(詞素切分),行三(語法標記),行四(華語翻譯)\n';
    sentences.forEach((s, i) => {
        const blocks = btn.closest('.igt-container').querySelectorAll('.igt-block');
        const block = blocks[i];
        const cols = block ? block.querySelectorAll('.igt-word-col') : [];
        const raws = s.words.map(w => w.raw).join('   ');
        const morphs = Array.from(cols).map(c => c.querySelector('.igt-l2').innerText.trim()).join('   ');
        const glosses = Array.from(cols).map(c => c.querySelector('.igt-l3').innerText.trim()).join('   ');
        const trans = s.translation || '';
        csv += `${i+1},"${raws.replace(/"/g,'""')}","${morphs.replace(/"/g,'""')}","${glosses.replace(/"/g,'""')}","${trans.replace(/"/g,'""')}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `igt_annotation_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
};

window.igtDownloadWord = async function(btn, sIdx) {
    const outputArea = btn.closest('.igt-output-area');
    const sentences = outputArea._glosserData || [];
    const blocks = btn.closest('.igt-container').querySelectorAll('.igt-block');
    
    // Build up-to-date data from editable fields
    const payload = { sentences: [] };
    blocks.forEach((block, i) => {
        const cols = block.querySelectorAll('.igt-word-col');
        const words = Array.from(cols).map(col => ({
            raw: col.dataset.raw,
            morph: col.querySelector('.igt-l2').innerText.trim(),
            gloss: col.querySelector('.igt-l3').innerText.trim(),
            confidence: 'high'
        }));
        const trans = block.querySelector('.igt-l4').innerText.replace(/^'|'$/g, '');
        payload.sentences.push({ words, translation: trans });
    });

    try {
        const res = await fetch('/api/download_word', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '太魯閣語IGT標注成果.docx';
        a.click();
    } catch(e) { alert('下載失敗，請確認標注後端已開啟。'); }
};

// AI Analysis Logic
document.addEventListener('DOMContentLoaded', () => {
    const analyzeBtn = document.getElementById('aiAnalyzeBtn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', async () => {
            const w1 = document.getElementById('aiWord1').value.trim();
            const w2 = document.getElementById('aiWord2').value.trim();
            const limit = document.getElementById('aiSentenceLimit').value;
            
            currentAiWord1 = w1;
            currentAiWord2 = w2;
            
            if (!w1) {
                alert('請至少輸入第一個詞彙進行分析！');
                return;
            }
            
            const loading = document.getElementById('ai-loading');
            const errorDiv = document.getElementById('ai-error');
            const resultContainer = document.getElementById('ai-result-container');
            const contentDiv = document.getElementById('ai-markdown-content');
            const statsInfo = document.getElementById('ai-stats-info');
            
            loading.classList.remove('hidden');
            errorDiv.classList.add('hidden');
            resultContainer.classList.add('hidden');
            analyzeBtn.disabled = true;
            
            try {
                const params = new URLSearchParams({ w1, limit });
                if (w2) params.append('w2', w2);
                
                const customApiKey = localStorage.getItem('custom_gemini_api_key') || "";
                if (customApiKey) params.append('custom_api_key', customApiKey);
                
                const response = await fetch(`/api/ai_analysis?${params.toString()}`);
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || '分析發生錯誤');
                }
                
                if (w2) {
                    statsInfo.innerHTML = `基於 <b>${data.w1_count}</b> 句 ${w1} 與 <b>${data.w2_count}</b> 句 ${w2} 例句進行分析`;
                } else {
                    statsInfo.innerHTML = `基於 <b>${data.w1_count}</b> 句 ${w1} 例句進行分析`;
                }
                
                // Parse markdown first
                let htmlContent = marked.parse(data.result);
                
                function escapeRegExp(string) {
                    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                }
                
                // Highlight keywords in HTML (only outside tags)
                if (w1) {
                    const regex1 = new RegExp('\\b(' + escapeRegExp(w1) + ')\\b(?![^<]*>)', 'gi');
                    htmlContent = htmlContent.replace(regex1, '<span style="color: #3b82f6; font-weight: bold;">$1</span>');
                }
                if (w2) {
                    const regex2 = new RegExp('\\b(' + escapeRegExp(w2) + ')\\b(?![^<]*>)', 'gi');
                    htmlContent = htmlContent.replace(regex2, '<span style="color: #ef4444; font-weight: bold;">$1</span>');
                }
                
                contentDiv.innerHTML = htmlContent;
                resultContainer.classList.remove('hidden');
                
            } catch (err) {
                errorDiv.innerHTML = err.message;
                errorDiv.classList.remove('hidden');
            } finally {
                loading.classList.add('hidden');
                analyzeBtn.disabled = false;
            }
        });
    }
});

// AI Analysis Export Functions
function exportToDoc() {
    const contentHtml = document.getElementById('ai-markdown-content').innerHTML;
    const header = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'><head><meta charset='utf-8'><title>太魯閣語語言學分析報告</title><style>body { color: #000000 !important; line-height: 1.8; font-family: sans-serif; }</style></head><body>`;
    const footer = `</body></html>`;
    const sourceHTML = header + contentHtml + footer;
    
    let filename = '太魯閣語語言學分析報告_' + currentAiWord1;
    if (currentAiWord2) filename += '&' + currentAiWord2;
    filename += '.doc';
    
    const source = 'data:application/vnd.ms-word;charset=utf-8,' + encodeURIComponent(sourceHTML);
    const fileDownload = document.createElement("a");
    document.body.appendChild(fileDownload);
    fileDownload.href = source;
    fileDownload.download = filename;
    fileDownload.click();
    document.body.removeChild(fileDownload);
}

function exportToPdf() {
    const element = document.getElementById('ai-markdown-content');
    
    // Temporarily set text color to black for PDF rendering
    const originalColor = element.style.color;
    element.style.color = '#000000';
    
    // Add a class to adjust typography for print
    element.classList.add('pdf-exporting');
    
    let filename = '太魯閣語語言學分析報告_' + currentAiWord1;
    if (currentAiWord2) filename += '&' + currentAiWord2;
    filename += '.pdf';
    
    const opt = {
        margin:       0.6,
        filename:     filename,
        image:        { type: 'jpeg', quality: 1.0 },
        html2canvas:  { scale: 4, useCORS: true, logging: false },
        jsPDF:        { unit: 'in', format: 'a4', orientation: 'portrait' },
        pagebreak:    { mode: ['css', 'avoid-all'] }
    };
    
    html2pdf().set(opt).from(element).save().then(() => {
        // Revert text color back to original after PDF is generated
        element.style.color = originalColor;
        element.classList.remove('pdf-exporting');
    });
}

// =========================================================
// 🏷️  語料標注頁籤 (Tab Glosser) — Full standalone logic
// =========================================================

let glosserSessionData = [];   // Stores all sentences from last batch run

// -- 1. Status Checker: polls port 8000 every 5s to show green/red dot --
async function checkGlosserStatus() {
    const dot  = document.getElementById('glosser-status-dot');
    const text = document.getElementById('glosser-status-text');
    if (!dot || !text) return;
    try {
        const res = await fetch('/', { signal: AbortSignal.timeout(2000) });
        if (res.ok) {
            dot.style.background  = '#4ade80';
            text.style.color      = '#4ade80';
            text.textContent      = '標注引擎就緒 (Port 8000)';
        } else { throw new Error(); }
    } catch {
        dot.style.background  = '#f87171';
        text.style.color      = '#f87171';
        text.textContent      = '引擎未啟動 (Port 8000)';
    }
}

// -- 2. Render IGT 4-line block into #glosser-results --
function renderGlosserIGT(sentences) {
    const container = document.getElementById('glosser-results');
    container.innerHTML = '';
    glosserSessionData = sentences;

    sentences.forEach((sentObj, sIdx) => {
        const words = sentObj.words || [];
        const translation = sentObj.translation || '';
        const originalLine = words.map(w => w.raw).join('  ');

        let groups = [];
        words.forEach((w, wIdx) => {
            const m = (w.morph || w.raw || '').trim();
            if (m.startsWith('=') && groups.length > 0) {
                groups[groups.length - 1].push({w, wIdx});
            } else {
                groups.push([{w, wIdx}]);
            }
        });

        const wordColsHtml = groups.map(group => {
            const cols = group.map(item => {
                const w = item.w;
                const wIdx = item.wIdx;
                const isLow = w.confidence === 'low';
                return `
                <div class="igt-word-col ${isLow ? 'igt-low-conf' : ''}"
                     data-raw="${(w.raw||'').replace(/"/g,"'")}"
                     data-sidx="${sIdx}" data-widx="${wIdx}">
                    <div class="igt-l2" contenteditable="true" title="詞素切分（可點擊編輯）">${(w.morph||w.raw).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
                    <div class="igt-l3" contenteditable="true" title="語法標記（可點擊編輯）">${(w.gloss||'').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
                </div>`;
            }).join('');
            return `<div class="igt-word-group" style="display:flex; gap:0;">${cols}</div>`;
        }).join('');

        const block = document.createElement('div');
        block.className = 'igt-block';
        block.dataset.sidx = sIdx;
        block.innerHTML = `
            <div style="font-size:0.75rem; color:#64748b; margin-bottom:0.5rem; font-weight:600;">句子成果 #${sIdx + 1}</div>
            <div class="igt-l1">${originalLine}</div>
            <div class="igt-words-row">${wordColsHtml}</div>
            <div class="igt-l4" contenteditable="true" title="華語意譯（可點擊編輯）">${translation}</div>
            <div class="igt-actions">
                <button class="igt-save-btn" onclick="glosserSaveSentence(this, ${sIdx})">💾 儲存至記憶庫</button>
                <button class="igt-csv-btn" style="background:#0ea5e9;color:white;border-color:#0284c7;" onclick="importToDictSentence(this)">📖 匯入為主辭典例句</button>
                <span class="igt-save-msg" style="color:#4ade80;font-size:0.8rem;display:none;">✅ 已儲存！</span>
            </div>
        `;
        container.appendChild(block);
    });
}

// -- 3. Analyze button handler --
document.addEventListener('DOMContentLoaded', () => {
    // Start status polling as soon as page loads
    checkGlosserStatus();
    setInterval(checkGlosserStatus, 6000);

    const btn = document.getElementById('glosserAnalyzeBtn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        let trukuText   = (document.getElementById('glosser-truku-input').value || '').trim();
        let chineseText = (document.getElementById('glosser-chinese-input').value || '').trim();

        if (!trukuText) { alert('請先輸入太魯閣語語料！'); return; }

        const loading  = document.getElementById('glosser-loading');
        const errorDiv = document.getElementById('glosser-error');
        const timer    = document.getElementById('glosser-timer');
        const results  = document.getElementById('glosser-results');
        const batchBar = document.getElementById('glosser-batch-bar');

        loading.classList.remove('hidden');
        errorDiv.classList.add('hidden');
        timer.classList.add('hidden');
        results.innerHTML = '';
        batchBar.classList.add('hidden');
        btn.disabled = true;

        // Smart sentence splitting (same as original glosser)
        trukuText   = trukuText.replace(/([.?])\s+/g, '$1\n').replace(/\n+/g, '\n');
        chineseText = chineseText.replace(/([。？!])\s*/g, '$1\n').replace(/\n+/g, '\n');

        const startTime = performance.now();
        try {
            const customApiKey = localStorage.getItem('custom_gemini_api_key') || "";
            const res = await fetch('/api/parse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ truku_sentence: trukuText, chinese_translation: chineseText, custom_api_key: customApiKey })
            });
            if (res.status === 429) throw new Error('QUOTA_EXCEEDED');
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
            const sentences = data.sentences || [];

            if (sentences.length === 0) throw new Error('AI 未回傳任何標注結果。');

            timer.classList.remove('hidden');
            timer.innerHTML = `⏱️ 批次標注完成！共處理 <b>${sentences.length}</b> 個句子，核心運算耗時 <b>${elapsed} 秒</b>。`;

            renderGlosserIGT(sentences);
            batchBar.classList.remove('hidden');

        } catch(e) {
            errorDiv.classList.remove('hidden');
            if (e.message.includes('QUOTA_EXCEEDED')) {
                errorDiv.innerHTML = `❌ 系統公用額度已用完！<br><small style="color:#f87171;">請通知作者，或點擊右上角「⚙️ API 設定」填寫您個人的免費金鑰後繼續使用。</small>`;
            } else {
                errorDiv.innerHTML = `❌ 標注失敗：${e.message}<br><small>請確認「語言學標注引擎」（Port 8000）已啟動且知識庫已就緒。</small>`;
            }
        } finally {
            loading.classList.add('hidden');
            btn.disabled = false;
        }
    });
});

// -- 4. Save one sentence to memory DB --
window.glosserSaveSentence = async function(btn, sIdx) {
    if (!confirm("確定要將這些單字校正儲存至記憶庫嗎？\n這將做為未來 AI 自動標注的黃金標準！")) return;
    const block = document.querySelector(`.igt-block[data-sidx="${sIdx}"]`);
    const words = Array.from(block.querySelectorAll('.igt-word-col')).map(col => ({
        raw:  col.dataset.raw,
        morph: col.querySelector('.igt-l2').innerText.trim(),
        gloss: col.querySelector('.igt-l3').innerText.trim()
    }));
    const msgEl = btn.nextElementSibling;
    try {
        const res = await fetch('/api/save_correct', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ words })
        });
        if (res.ok) {
            msgEl.style.display = 'inline';
            setTimeout(() => { msgEl.style.display = 'none'; }, 3000);
            alert("✅ 儲存成功！");
            
            try {
                const trukuSentence = block.querySelector('.igt-l1').innerText.trim();
                const chineseTranslation = block.querySelector('.igt-l4').innerText.trim();
                
                const checkRes = await fetch('/api/dictionary/check_sentence', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ truku_sentence: trukuSentence })
                });
                if (checkRes.ok) {
                    const checkData = await checkRes.json();
                    if (!checkData.exists) {
                        if (confirm(`發現這整句例句目前不在主辭典中：\n\n${trukuSentence}\n\n請問要順便將它新增到主辭典嗎？（邊標注、邊擴充）`)) {
                            await fetch('/api/dictionary/add_sentence', {
                                method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ truku_sentence: trukuSentence, chinese_translation: chineseTranslation })
                            });
                            alert("✅ 例句擴充成功！");
                        }
                    }
                }
            } catch(e) { console.error(e); }
        } else { throw new Error(); }
    } catch { alert('儲存失敗，請確認標注後端已開啟。'); }
};

window.importToDictSentence = async function(btn) {
    if (!confirm("確定要將這句話與意譯「匯入主辭典」作為標準例句嗎？")) return;
    const block = btn.closest('.igt-block');
    const trukuSentence = block.querySelector('.igt-l1').innerText.trim();
    const chineseTranslation = block.querySelector('.igt-l4').innerText.trim();
    const oldText = btn.innerHTML;
    btn.innerHTML = '匯入中...';
    btn.disabled = true;
    try {
        const res = await fetch('/api/dictionary/add_sentence', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ truku_sentence: trukuSentence, chinese_translation: chineseTranslation })
        });
        if (res.ok) {
            btn.innerHTML = '✅ 已匯入主辭典';
            alert("✅ 匯入成功！此句已新增至主系統辭典庫中。");
            setTimeout(() => { btn.innerHTML = oldText; btn.disabled = false; }, 3000);
        } else { throw new Error(); }
    } catch(e) {
        btn.innerHTML = '❌ 匯入失敗';
        setTimeout(() => { btn.innerHTML = oldText; btn.disabled = false; }, 3000);
    }
};

// -- 5. Batch CSV export from the glosser tab --
window.glosserBatchCsv = function() {
    const blocks = document.querySelectorAll('#glosser-results .igt-block');
    if (!blocks.length) return;
    let csv = '\uFEFF句子編號,行一(原文),行二(詞素切分),行三(語法標記),行四(華語翻譯)\n';
    blocks.forEach((block, i) => {
        const l1 = block.querySelector('.igt-l1').innerText.trim();
        const cols = block.querySelectorAll('.igt-word-col');
        const morphs  = Array.from(cols).map(c => c.querySelector('.igt-l2').innerText.trim()).join('   ');
        const glosses = Array.from(cols).map(c => c.querySelector('.igt-l3').innerText.trim()).join('   ');
        const l4 = block.querySelector('.igt-l4').innerText.replace(/^'|'$/g,'').trim();
        csv += `${i+1},"${l1.replace(/"/g,'""')}","${morphs.replace(/"/g,'""')}","${glosses.replace(/"/g,'""')}","${l4.replace(/"/g,'""')}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `太魯閣語IGT標注_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
};

// -- 6. Batch Word export from the glosser tab --
window.glosserBatchWord = async function() {
    const blocks = document.querySelectorAll('#glosser-results .igt-block');
    if (!blocks.length) return;
    const payload = { sentences: [] };
    blocks.forEach(block => {
        const cols = block.querySelectorAll('.igt-word-col');
        const words = Array.from(cols).map(col => ({
            raw:   col.dataset.raw,
            morph: col.querySelector('.igt-l2').innerText.trim(),
            gloss: col.querySelector('.igt-l3').innerText.trim(),
            confidence: 'high'
        }));
        const trans = block.querySelector('.igt-l4').innerText.replace(/^'|'$/g,'').trim();
        payload.sentences.push({ words, translation: trans });
    });
    try {
        const res = await fetch('/api/download_word', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `太魯閣語IGT標注成果_${new Date().toISOString().slice(0,10)}.docx`;
        a.click();
    } catch(e) { alert('下載失敗，請確認標注後端已開啟。'); }
};

// -- 7. Bridge: fill glosser tab from a search result sentence --
window.sendToGlosser = function(trukuSentence, chineseTranslation) {
    // Switch to glosser tab
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
    document.querySelector('[data-tab="tab-glosser"]').classList.add('active');
    document.getElementById('tab-glosser').classList.remove('hidden');

    // Pre-fill input fields
    document.getElementById('glosser-truku-input').value   = trukuSentence;
    document.getElementById('glosser-chinese-input').value = chineseTranslation || '';

    // Scroll up and auto-click analyze
    document.getElementById('glosser-truku-input').scrollIntoView({ behavior: 'smooth' });
    setTimeout(() => { document.getElementById('glosserAnalyzeBtn').click(); }, 400);
};

// =========================================================
// ☀️  Theme Toggle Logic (Light / Dark Mode)
// =========================================================
document.addEventListener('DOMContentLoaded', () => {
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    if (!themeToggleBtn) return;

    // Default to dark mode unless 'light' is saved
    const savedTheme = localStorage.getItem('truku-dict-theme');
    if (savedTheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        themeToggleBtn.innerHTML = '🌙 暗色模式';
    }

    themeToggleBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        if (currentTheme === 'light') {
            document.documentElement.removeAttribute('data-theme'); // reverts to dark (default)
            localStorage.setItem('truku-dict-theme', 'dark');
            themeToggleBtn.innerHTML = '☀️ 亮色模式';
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem('truku-dict-theme', 'light');
            themeToggleBtn.innerHTML = '🌙 暗色模式';
        }
    });
});
