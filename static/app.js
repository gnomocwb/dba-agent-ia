// DBA Agent Studio - Frontend Logic

let appState = {
  connections: [],
  activeConnectionId: null,
  activeMetrics: null,
  chatHistory: [],
  config: {}
};

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initEventListeners();
  loadConfig();
  loadConnections();
});

// 1. TABS
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));

      tab.classList.add("active");
      const targetId = tab.dataset.tab;
      const panel = document.getElementById(targetId);
      if (panel) panel.classList.add("active");
    });
  });
}

function switchToTab(tabId) {
  const tabBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (tabBtn) tabBtn.click();
}

// 2. EVENT LISTENERS
function initEventListeners() {
  // Selector de Banco Ativo
  document.getElementById("activeDbSelect").addEventListener("change", (e) => {
    appState.activeConnectionId = e.target.value;
    if (appState.activeConnectionId) {
      fetchMetrics(appState.activeConnectionId);
    }
  });

  // Botões de Ação Topo
  document.getElementById("btnRefreshMetrics").addEventListener("click", () => {
    if (appState.activeConnectionId) {
      fetchMetrics(appState.activeConnectionId);
    } else {
      alert("Por favor, selecione uma conexão de banco de dados primeiro.");
    }
  });

  document.getElementById("btnTriggerAnalysis").addEventListener("click", () => {
    triggerAiAnalysis();
  });

  document.getElementById("btnReanalyze").addEventListener("click", () => {
    triggerAiAnalysis();
  });

  // Chat
  const chatForm = document.getElementById("chatForm");
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendChatMessage();
  });

  document.querySelectorAll(".quick-prompt").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const promptText = e.target.dataset.prompt;
      document.getElementById("chatInput").value = promptText;
      sendChatMessage();
    });
  });

  document.getElementById("btnClearChat").addEventListener("click", () => {
    appState.chatHistory = [];
    document.getElementById("chatMessages").innerHTML = `
      <div class="message agent">
        <div class="msg-avatar">DBA</div>
        <div class="msg-bubble">Histórico de conversa limpo. Como posso ajudar com seu banco agora?</div>
      </div>
    `;
  });

  // Modal de Conexões
  document.getElementById("btnOpenNewConnModal").addEventListener("click", () => {
    openConnModal();
  });

  document.getElementById("btnCloseModal").addEventListener("click", () => {
    closeConnModal();
  });

  document.getElementById("formDbType").addEventListener("change", (e) => {
    updateModalFormFields(e.target.value);
  });

  document.getElementById("btnTestConnInModal").addEventListener("click", () => {
    testConnectionFromModal();
  });

  document.getElementById("connectionForm").addEventListener("submit", (e) => {
    e.preventDefault();
    saveConnectionFromModal();
  });

  // Configurações
  document.getElementById("settingsForm").addEventListener("submit", (e) => {
    e.preventDefault();
    saveConfig();
  });
}

// 3. API & DATA LOADING
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    appState.config = data;
    
    const statusSmall = document.getElementById("settingApiKeyStatus");
    if (data.has_api_key) {
      statusSmall.innerHTML = `✓ Chave ativa detectada (${data.gemini_api_key_masked || "Pronta para uso"}).`;
      statusSmall.style.color = "var(--success)";
    } else {
      statusSmall.innerHTML = `⚠️ Nenhuma chave de API configurada. O Gemini requer uma chave.`;
      statusSmall.style.color = "var(--warning)";
    }

    if (data.gemini_model) {
      document.getElementById("settingModel").value = data.gemini_model;
    }
  } catch (err) {
    console.error("Erro ao carregar configurações:", err);
  }
}

async function saveConfig() {
  const apiKey = document.getElementById("settingApiKey").value.trim();
  const model = document.getElementById("settingModel").value;

  try {
    const payload = { gemini_model: model };
    if (apiKey) payload.gemini_api_key = apiKey;

    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      alert("Configurações salvas com sucesso!");
      loadConfig();
    }
  } catch (err) {
    alert("Erro ao salvar configurações: " + err.message);
  }
}

async function loadConnections() {
  try {
    const res = await fetch("/api/connections");
    const data = await res.json();
    appState.connections = data.connections || [];

    renderConnectionSelect();
    renderConnectionsTab();

    // Se nenhum banco ativo estiver selecionado, seleciona o primeiro
    if (!appState.activeConnectionId && appState.connections.length > 0) {
      appState.activeConnectionId = appState.connections[0].id;
      document.getElementById("activeDbSelect").value = appState.activeConnectionId;
      fetchMetrics(appState.activeConnectionId);
    }
  } catch (err) {
    console.error("Erro ao carregar conexões:", err);
  }
}

function getDbBadge(type) {
  if (type === "postgres") return { icon: "🐘", label: "PostgreSQL" };
  if (type === "mariadb" || type === "mysql") return { icon: "🐬", label: "MariaDB" };
  if (type === "datastore" || type === "google_datastore") return { icon: "☁️", label: "Google Datastore" };
  if (type === "featurestore" || type === "google_featurestore") return { icon: "🧠", label: "Vertex AI Feature Store" };
  return { icon: "💾", label: type };
}

function renderConnectionSelect() {
  const select = document.getElementById("activeDbSelect");
  select.innerHTML = "";

  if (appState.connections.length === 0) {
    select.innerHTML = `<option value="">Nenhum banco cadastrado</option>`;
    return;
  }

  appState.connections.forEach(conn => {
    const badge = getDbBadge(conn.db_type);
    const opt = document.createElement("option");
    opt.value = conn.id;
    opt.textContent = `${badge.icon} ${conn.name} (${conn.database || conn.project_id || 'GCP'})`;
    if (conn.id === appState.activeConnectionId) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });
}

function renderConnectionsTab() {
  const container = document.getElementById("connectionsList");
  container.innerHTML = "";

  if (appState.connections.length === 0) {
    container.innerHTML = `<p style="color:var(--text-dim)">Nenhuma conexão configurada. Clique em 'Nova Conexão' para adicionar.</p>`;
    return;
  }

  appState.connections.forEach(conn => {
    const badge = getDbBadge(conn.db_type);
    const isActive = conn.id === appState.activeConnectionId;
    const isGcp = conn.db_type === "datastore" || conn.db_type === "featurestore";

    const card = document.createElement("div");
    card.className = `conn-card ${isActive ? 'active-conn' : ''}`;
    card.innerHTML = `
      <div>
        <div class="conn-title">
          <span>${badge.icon}</span>
          <span>${escapeHtml(conn.name)}</span>
          ${isActive ? '<span class="badge badge-success" style="font-size:0.65rem;">Ativo</span>' : ''}
        </div>
        <div class="conn-meta" style="margin-top:0.75rem;">
          <div><strong>Tipo:</strong> ${badge.label}</div>
          ${isGcp ? `
            <div><strong>Project ID:</strong> <code>${conn.project_id || conn.database}</code></div>
            ${conn.location ? `<div><strong>Região:</strong> ${conn.location}</div>` : ''}
            ${conn.database_id ? `<div><strong>Database ID:</strong> ${conn.database_id}</div>` : ''}
          ` : `
            <div><strong>Host:</strong> ${conn.host}:${conn.port}</div>
            <div><strong>Base:</strong> <code>${conn.database}</code></div>
            <div><strong>Usuário:</strong> ${conn.user}</div>
          `}
        </div>
      </div>

      <div class="conn-actions">
        <button class="btn btn-secondary btn-sm" onclick="testConnectionById('${conn.id}')">Testar</button>
        <button class="btn btn-primary btn-sm" onclick="setActiveConnection('${conn.id}')">Conectar</button>
        <button class="btn btn-danger btn-sm" onclick="deleteConnectionById('${conn.id}')">Excluir</button>
      </div>
    `;
    container.appendChild(card);
  });
}

function setActiveConnection(connId) {
  appState.activeConnectionId = connId;
  document.getElementById("activeDbSelect").value = connId;
  renderConnectionsTab();
  fetchMetrics(connId);
  switchToTab("tab-dashboard");
}

async function testConnectionById(connId) {
  const conn = appState.connections.find(c => c.id === connId);
  if (!conn) return;

  const btn = event?.target;
  const originalText = btn ? btn.textContent : "";
  if (btn) btn.innerHTML = `<span class="spinner" style="width:12px;height:12px"></span>`;

  try {
    const res = await fetch("/api/test-connection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(conn)
    });
    const result = await res.json();
    if (result.success) {
      alert(`✅ Conectado com sucesso!\nVersão: ${result.version}`);
    } else {
      alert(`❌ Falha de conexão:\n${result.error || result.message}`);
    }
  } catch (err) {
    alert("Erro na requisição: " + err.message);
  } finally {
    if (btn) btn.textContent = originalText;
  }
}

async function deleteConnectionById(connId) {
  if (!confirm("Tem certeza que deseja remover esta conexão?")) return;
  try {
    const res = await fetch(`/api/connections/${connId}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      if (appState.activeConnectionId === connId) {
        appState.activeConnectionId = null;
      }
      loadConnections();
    }
  } catch (err) {
    alert("Erro ao excluir: " + err.message);
  }
}

// 4. METRICS FETCH & RENDER
async function fetchMetrics(connId) {
  const refreshBtn = document.getElementById("btnRefreshMetrics");
  refreshBtn.innerHTML = `<span class="spinner"></span> Coletando...`;
  refreshBtn.disabled = true;

  try {
    const res = await fetch(`/api/metrics/${connId}`);
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Erro ao consultar métricas");
    }
    const metrics = await res.json();
    appState.activeMetrics = metrics;
    renderMetrics(metrics);
  } catch (err) {
    alert("Erro ao coletar métricas do banco: " + err.message);
  } finally {
    refreshBtn.innerHTML = `🔄 Coletar Métricas`;
    refreshBtn.disabled = false;
  }
}

function renderMetrics(metrics) {
  const isPostgres = metrics.db_type === "postgres";
  const isDatastore = metrics.db_type === "datastore" || metrics.db_type === "google_datastore";
  const isFeatureStore = metrics.db_type === "featurestore" || metrics.db_type === "google_featurestore";

  // 1. KPI Health Score
  const scoreData = metrics.preliminary_score || { score: "--", status: "Aguardando", badge_class: "info" };
  document.getElementById("kpiHealthScore").innerHTML = `${scoreData.score} <span style="font-size:1rem;color:var(--text-dim)">/ 100</span>`;
  document.getElementById("kpiHealthBadge").innerHTML = `<span class="badge badge-${scoreData.badge_class}">${scoreData.status}</span>`;

  // 2. KPI Cache Hit Ratio / Kinds / Featurestores
  if (isDatastore) {
    document.querySelector(".kpi-card:nth-child(2) .kpi-title").textContent = "Total Kinds";
    document.getElementById("kpiCacheHit").textContent = metrics.total_kinds_count || 0;
    document.getElementById("kpiCacheSub").textContent = "Tipos de Entidades";
  } else if (isFeatureStore) {
    document.querySelector(".kpi-card:nth-child(2) .kpi-title").textContent = "Featurestores";
    document.getElementById("kpiCacheHit").textContent = metrics.total_featurestores || 0;
    document.getElementById("kpiCacheSub").textContent = "Lojas de Features Ativas";
  } else {
    document.querySelector(".kpi-card:nth-child(2) .kpi-title").textContent = "Cache Hit Ratio";
    const cacheHit = metrics.cache_hit_ratio !== null ? `${metrics.cache_hit_ratio}%` : "N/A";
    document.getElementById("kpiCacheHit").textContent = cacheHit;
    document.getElementById("kpiCacheSub").textContent = "Eficiência da memória RAM";
  }

  // 3. KPI Conexões / Entidades / Entity Types
  if (isDatastore) {
    document.querySelector(".kpi-card:nth-child(3) .kpi-title").textContent = "Total Entidades";
    document.getElementById("kpiConnections").textContent = (metrics.total_entities_count || 0).toLocaleString();
    document.getElementById("kpiConnSub").textContent = "Registros indexados";
  } else if (isFeatureStore) {
    document.querySelector(".kpi-card:nth-child(3) .kpi-title").textContent = "Entity Types";
    document.getElementById("kpiConnections").textContent = metrics.total_entity_types || 0;
    document.getElementById("kpiConnSub").textContent = "Entidades monitoradas";
  } else {
    document.querySelector(".kpi-card:nth-child(3) .kpi-title").textContent = "Conexões Ativas";
    const totalConns = (metrics.connections_summary || []).reduce((acc, c) => acc + (c.count || 0), 0);
    document.getElementById("kpiConnections").textContent = totalConns;
    document.getElementById("kpiConnSub").textContent = "Sessões conectadas";
  }

  // 4. KPI Específico
  if (isDatastore) {
    document.getElementById("kpi4Title").textContent = "Tamanho Total";
    const sizeMb = metrics.total_bytes ? (metrics.total_bytes / (1024 * 1024)).toFixed(2) + " MB" : "0 MB";
    document.getElementById("kpi4Value").textContent = sizeMb;
    document.getElementById("kpi4Sub").textContent = "Armazenamento na GCP";
  } else if (isFeatureStore) {
    document.getElementById("kpi4Title").textContent = "Total Features";
    document.getElementById("kpi4Value").textContent = metrics.total_features || 0;
    document.getElementById("kpi4Sub").textContent = `${metrics.online_serving_nodes || 0} nós online`;
  } else if (isPostgres) {
    document.getElementById("kpi4Title").textContent = "Total Linhas Mortas";
    const totalDead = (metrics.vacuum_stats || []).reduce((acc, v) => acc + (v.dead_rows || 0), 0);
    document.getElementById("kpi4Value").textContent = totalDead.toLocaleString();
    document.getElementById("kpi4Sub").textContent = "Necessidade de VACUUM";
  } else {
    document.getElementById("kpi4Title").textContent = "Temp Tables em Disco";
    const status = metrics.status_variables || {};
    document.getElementById("kpi4Value").textContent = status.Created_tmp_disk_tables || "0";
    document.getElementById("kpi4Sub").textContent = `De ${status.Created_tmp_tables || 0} criadas`;
  }

  // Alertas Preliminares
  const alertsContainer = document.getElementById("preliminaryAlertsContainer");
  const alertsList = document.getElementById("preliminaryAlertsList");
  alertsList.innerHTML = "";
  if (scoreData.deductions && scoreData.deductions.length > 0) {
    scoreData.deductions.forEach(d => {
      const li = document.createElement("li");
      li.textContent = d;
      alertsList.appendChild(li);
    });
    alertsContainer.style.display = "block";
  } else {
    alertsContainer.style.display = "none";
  }

  // Tabela: Consultas Lentas / Kinds / Entity Types
  renderSlowQueriesTable(metrics);

  // Tabela: Scans / Hotspots / Drift
  renderScansTable(metrics);

  // Tabela: Tamanho / Propriedades / Serving
  renderSizesTable(metrics);

  // Tabela: Configurações
  renderSettingsTable(metrics);
}

function renderSlowQueriesTable(metrics) {
  const tbody = document.querySelector("#tableSlowQueries tbody");
  const thead = document.querySelector("#tableSlowQueries thead");
  tbody.innerHTML = "";

  const isDatastore = metrics.db_type === "datastore" || metrics.db_type === "google_datastore";
  const isFeatureStore = metrics.db_type === "featurestore" || metrics.db_type === "google_featurestore";

  if (isDatastore) {
    document.querySelector("#tableSlowQueries").closest(".card-section").querySelector(".section-title span").textContent = "📊 Kinds e Tipos de Entidades (Datastore)";
    thead.innerHTML = `
      <tr>
        <th style="width: 40%;">Kind (Tipo de Entidade)</th>
        <th style="width: 20%;">Entidades Estimadas</th>
        <th style="width: 20%;">Tamanho Dados</th>
        <th style="width: 20%;">Tamanho Índices</th>
      </tr>
    `;
    const kinds = metrics.kinds_summary || [];
    if (kinds.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding: 1.5rem;">Nenhum Kind encontrado no Datastore ou estatísticas ainda não agregadas pela GCP.</td></tr>`;
      return;
    }
    kinds.forEach(k => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${escapeHtml(k.kind_name)}</code></td>
        <td><strong>${(k.estimated_rows || 0).toLocaleString()}</strong></td>
        <td>${k.data_size_mb} MB</td>
        <td>${k.index_size_mb} MB</td>
      `;
      tbody.appendChild(tr);
    });
    return;
  }

  if (isFeatureStore) {
    document.querySelector("#tableSlowQueries").closest(".card-section").querySelector(".section-title span").textContent = "🧠 Catálogo de Featurestores & Entity Types";
    thead.innerHTML = `
      <tr>
        <th style="width: 35%;">Featurestore / Entity Type</th>
        <th style="width: 20%;">Total Features</th>
        <th style="width: 25%;">Monitoramento de Drift</th>
        <th style="width: 20%;">Amostra Features</th>
      </tr>
    `;
    const fsList = metrics.featurestores_summary || [];
    if (fsList.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding: 1.5rem;">Nenhum Featurestore registrado no projeto/região especificado.</td></tr>`;
      return;
    }
    fsList.forEach(fs => {
      (fs.entity_types || []).forEach(et => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>${escapeHtml(fs.name)}</strong> / <code>${escapeHtml(et.name)}</code></td>
          <td><strong>${et.features_count}</strong></td>
          <td><span class="badge ${et.monitoring_enabled ? 'badge-success' : 'badge-warning'}">${et.monitoring_enabled ? '✓ Ativo' : '⚠️ Desativado'}</span></td>
          <td style="font-size:0.75rem; color:var(--text-dim);">${(et.features_sample || []).join(', ') || '-'}</td>
        `;
        tbody.appendChild(tr);
      });
    });
    return;
  }

  // Relacional (Postgres / MariaDB)
  document.querySelector("#tableSlowQueries").closest(".card-section").querySelector(".section-title span").textContent = "🐢 Consultas Lentas & Consumo de Tempo";
  thead.innerHTML = `
    <tr>
      <th style="width: 55%;">Consulta SQL</th>
      <th style="width: 15%;">Chamadas</th>
      <th style="width: 15%;">Tempo Total</th>
      <th style="width: 15%;">Tempo Médio</th>
    </tr>
  `;

  const slow = metrics.slow_queries || [];
  if (slow.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding: 1.5rem;">Nenhuma consulta lenta detectada no momento. Ótimo sinal!</td></tr>`;
    return;
  }

  slow.forEach(q => {
    const tr = document.createElement("tr");
    const queryText = escapeHtml(q.query || "");
    const calls = q.calls ?? "1";
    const totalTime = q.total_time_ms ? `${q.total_time_ms} ms` : (q.duration_ms ? `${Math.round(q.duration_ms)} ms` : "-");
    const meanTime = q.mean_time_ms ? `${q.mean_time_ms} ms` : "-";

    tr.innerHTML = `
      <td><code style="white-space: pre-wrap; word-break: break-all; max-height: 80px; display: block; overflow-y: auto;">${queryText}</code></td>
      <td><strong>${calls}</strong></td>
      <td><span style="color:var(--warning); font-weight:600;">${totalTime}</span></td>
      <td>${meanTime}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderScansTable(metrics) {
  const tbody = document.querySelector("#tableScans tbody");
  tbody.innerHTML = "";

  if (metrics.db_type === "datastore" || metrics.db_type === "google_datastore") {
    const hotspots = metrics.hotspot_risks || [];
    if (hotspots.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--success);">✓ Nenhum hotspot de escrita sequencial detectado nas amostras de chave.</td></tr>`;
      return;
    }
    hotspots.forEach(h => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(h.kind)}</strong></td>
        <td colspan="3"><span class="badge badge-danger">⚠️ ${escapeHtml(h.reason)}</span></td>
      `;
      tbody.appendChild(tr);
    });
    return;
  }

  if (metrics.db_type === "featurestore" || metrics.db_type === "google_featurestore") {
    const alerts = metrics.drift_alerts || [];
    if (alerts.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--success);">✓ Todas as features monitoradas sem alertas de drift.</td></tr>`;
      return;
    }
    alerts.forEach(a => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(a.type)}</strong></td>
        <td colspan="3"><span class="badge badge-${a.severity === 'warning' ? 'warning' : 'info'}">${escapeHtml(a.message)}</span></td>
      `;
      tbody.appendChild(tr);
    });
    return;
  }

  if (metrics.db_type === "postgres") {
    const scans = metrics.table_scans || [];
    if (scans.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-dim);">Nenhum scan registrado.</td></tr>`;
      return;
    }

    scans.forEach(s => {
      const tr = document.createElement("tr");
      const pct = s.seq_scan_pct ?? 0;
      const isHighSeq = pct > 60 && (s.seq_scan > 50);
      tr.innerHTML = `
        <td><strong>${escapeHtml(s.table_name)}</strong></td>
        <td>${s.seq_scan?.toLocaleString() || 0}</td>
        <td>${s.idx_scan?.toLocaleString() || 0}</td>
        <td>
          <span class="badge ${isHighSeq ? 'badge-danger' : 'badge-success'}">
            ${pct}% ${isHighSeq ? '⚠️' : ''}
          </span>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } else {
    // MariaDB
    const noPk = metrics.tables_without_pk || [];
    if (noPk.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--success);">✓ Todas as tabelas possuem Chave Primária definida!</td></tr>`;
      return;
    }
    noPk.forEach(tab => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(tab)}</strong></td>
        <td colspan="3"><span class="badge badge-danger">SEM CHAVE PRIMÁRIA</span></td>
      `;
      tbody.appendChild(tr);
    });
  }
}

function renderSizesTable(metrics) {
  const tbody = document.querySelector("#tableSizes tbody");
  tbody.innerHTML = "";

  if (metrics.db_type === "datastore" || metrics.db_type === "google_datastore") {
    const props = metrics.properties_summary || [];
    if (props.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-dim);">Nenhuma propriedade mapeada ainda.</td></tr>`;
      return;
    }
    props.forEach(p => {
      const tr = document.createElement("tr");
      const propNames = (p.properties || []).map(pr => pr.property).slice(0, 5).join(", ");
      tr.innerHTML = `
        <td><strong>${escapeHtml(p.kind)}</strong></td>
        <td>${p.properties?.length || 0} props</td>
        <td colspan="3" style="font-size:0.8rem; color:var(--text-dim);">${escapeHtml(propNames)}...</td>
      `;
      tbody.appendChild(tr);
    });
    return;
  }

  if (metrics.db_type === "featurestore" || metrics.db_type === "google_featurestore") {
    const fsList = metrics.featurestores_summary || [];
    if (fsList.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-dim);">Nenhum Featurestore listado.</td></tr>`;
      return;
    }
    fsList.forEach(fs => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(fs.name)}</strong></td>
        <td>${fs.entity_types?.length || 0} tipos</td>
        <td>${fs.online_serving_nodes} nós fixos</td>
        <td colspan="2" style="font-size:0.8rem;">Criado: ${escapeHtml(fs.create_time?.substring(0, 19) || '-')}</td>
      `;
      tbody.appendChild(tr);
    });
    return;
  }

  const sizes = metrics.table_sizes || [];
  if (sizes.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-dim);">Nenhum dado de tabela encontrado.</td></tr>`;
    return;
  }

  sizes.forEach(s => {
    const tr = document.createElement("tr");
    if (metrics.db_type === "postgres") {
      tr.innerHTML = `
        <td><strong>${escapeHtml(s.table_name)}</strong></td>
        <td>-</td>
        <td>${s.data_size || '-'}</td>
        <td>${s.index_size || '-'}</td>
        <td><strong>${s.total_size || '-'}</strong></td>
      `;
    } else {
      tr.innerHTML = `
        <td><strong>${escapeHtml(s.table_name)}</strong></td>
        <td>${s.estimated_rows?.toLocaleString() || 0}</td>
        <td>${s.data_size_mb} MB</td>
        <td>${s.index_size_mb} MB</td>
        <td><strong>${s.total_size_mb} MB</strong></td>
      `;
    }
    tbody.appendChild(tr);
  });
}

function renderSettingsTable(metrics) {
  const tbody = document.querySelector("#tableSettings tbody");
  tbody.innerHTML = "";

  const settings = metrics.key_settings || [];
  if (settings.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:var(--text-dim);">Configurações não extraídas.</td></tr>`;
    return;
  }

  settings.forEach(st => {
    const tr = document.createElement("tr");
    const name = st.name || st.Variable_name;
    const val = st.setting ? `${st.setting} ${st.unit || ''}` : st.Value;
    const desc = st.short_desc || "Parâmetro do engine";

    tr.innerHTML = `
      <td><code>${escapeHtml(name)}</code></td>
      <td><strong>${escapeHtml(String(val))}</strong></td>
      <td style="color:var(--text-muted); font-size:0.8rem;">${escapeHtml(desc)}</td>
    `;
    tbody.appendChild(tr);
  });
}

// 5. AI AUDIT & REPORT
async function triggerAiAnalysis() {
  if (!appState.activeConnectionId) {
    alert("Selecione um banco de dados antes de gerar a análise.");
    return;
  }

  switchToTab("tab-ai-report");
  const loading = document.getElementById("aiLoadingContainer");
  const reportBox = document.getElementById("aiReportContainer");

  loading.style.display = "block";
  reportBox.style.display = "none";

  try {
    const res = await fetch(`/api/analyze/${appState.activeConnectionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: appState.config.gemini_model || "gemini-3.5-flash-lite"
      })
    });
    const data = await res.json();

    if (!data.success) {
      throw new Error(data.error || "Falha na análise da IA");
    }

    // Renderiza Markdown
    const htmlContent = marked.parse(data.analysis_markdown);
    reportBox.innerHTML = htmlContent;

    // Adiciona botão "Copiar SQL" aos blocos de código
    attachCopyButtons(reportBox);

    reportBox.style.display = "block";
  } catch (err) {
    reportBox.innerHTML = `
      <div style="color: var(--danger); padding: 1.5rem; border: 1px solid var(--danger); border-radius: 8px;">
        <h3>Erro ao Gerar Diagnóstico com IA</h3>
        <p style="margin-top: 0.5rem;">${escapeHtml(err.message)}</p>
        <p style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-muted);">
          Verifique sua chave de API na aba <strong>Configurações</strong>.
        </p>
      </div>
    `;
    reportBox.style.display = "block";
  } finally {
    loading.style.display = "none";
  }
}

function attachCopyButtons(container) {
  const codeBlocks = container.querySelectorAll("pre");
  codeBlocks.forEach(pre => {
    const btn = document.createElement("button");
    btn.className = "copy-code-btn";
    btn.textContent = "Copiar SQL";
    btn.addEventListener("click", () => {
      const code = pre.querySelector("code")?.innerText || pre.innerText;
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = "Copiado!";
        setTimeout(() => { btn.textContent = "Copiar SQL"; }, 2000);
      });
    });
    pre.appendChild(btn);
  });
}

// 6. CHAT
async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  appendChatMessage("user", message);

  // Loading indicador
  const loadingId = "msg-loading-" + Date.now();
  appendChatMessage("agent", `<span class="spinner" style="width:14px;height:14px"></span> Consultando DBA Copilot...`, loadingId);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        history: appState.chatHistory,
        connection_id: appState.activeConnectionId,
        model: appState.config.gemini_model || "gemini-3.5-flash-lite"
      })
    });
    const data = await res.json();

    // Remove mensagem temporária
    const loadingElem = document.getElementById(loadingId);
    if (loadingElem) loadingElem.remove();

    appendChatMessage("agent", data.reply);

    // Salva histórico
    appState.chatHistory.push({ role: "user", content: message });
    appState.chatHistory.push({ role: "model", content: data.reply });

  } catch (err) {
    const loadingElem = document.getElementById(loadingId);
    if (loadingElem) loadingElem.remove();
    appendChatMessage("agent", `⚠️ Erro ao obter resposta: ${err.message}`);
  }
}

function appendChatMessage(role, content, customId = null) {
  const container = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = `message ${role}`;
  if (customId) div.id = customId;

  const isAgent = role === "agent";
  const avatar = isAgent ? "🧠" : "Você";
  const parsedContent = isAgent ? marked.parse(content) : escapeHtml(content);

  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-bubble">${parsedContent}</div>
  `;

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;

  if (isAgent) {
    attachCopyButtons(div);
  }
}

function updateModalFormFields(dbType) {
  const isGcp = dbType === "datastore" || dbType === "featurestore";
  const secRel = document.getElementById("sectionRelational");
  const secGcp = document.getElementById("sectionGcp");

  if (isGcp) {
    if (secRel) secRel.style.display = "none";
    if (secGcp) secGcp.style.display = "block";
  } else {
    if (secRel) secRel.style.display = "block";
    if (secGcp) secGcp.style.display = "none";

    const portInput = document.getElementById("formPort");
    if (portInput) {
      if (dbType === "postgres") {
        portInput.value = "5432";
        document.getElementById("formEncoding").value = "latin1";
      } else {
        portInput.value = "3306";
        document.getElementById("formEncoding").value = "utf8mb4";
      }
    }
  }
}

// 7. MODAL CONEXÕES
function openConnModal(conn = null) {
  const modal = document.getElementById("connModal");
  const testBox = document.getElementById("testResultBox");
  testBox.style.display = "none";

  if (conn) {
    document.getElementById("modalTitleText").textContent = "Editar Conexão";
    document.getElementById("formConnId").value = conn.id;
    document.getElementById("formDbType").value = conn.db_type;
    document.getElementById("formConnName").value = conn.name;
    document.getElementById("formHost").value = conn.host || "";
    document.getElementById("formPort").value = conn.port || 5432;
    document.getElementById("formDatabase").value = conn.database || "";
    document.getElementById("formUser").value = conn.user || "";
    document.getElementById("formPassword").value = "";
    document.getElementById("formEncoding").value = conn.client_encoding || "";

    document.getElementById("formGcpProject").value = conn.project_id || conn.database || "";
    document.getElementById("formGcpKeyPath").value = conn.credentials_path || "";
    document.getElementById("formGcpLocation").value = conn.location || "us-central1";
    document.getElementById("formGcpDatastoreDb").value = conn.database_id || "(default)";

    updateModalFormFields(conn.db_type);
  } else {
    document.getElementById("modalTitleText").textContent = "Cadastrar Nova Conexão";
    document.getElementById("formConnId").value = "";
    document.getElementById("formDbType").value = "postgres";
    document.getElementById("formConnName").value = "";
    document.getElementById("formHost").value = "localhost";
    document.getElementById("formPort").value = "5432";
    document.getElementById("formDatabase").value = "";
    document.getElementById("formUser").value = "";
    document.getElementById("formPassword").value = "";
    document.getElementById("formEncoding").value = "latin1";

    document.getElementById("formGcpProject").value = "";
    document.getElementById("formGcpKeyPath").value = "";
    document.getElementById("formGcpLocation").value = "us-central1";
    document.getElementById("formGcpDatastoreDb").value = "(default)";

    updateModalFormFields("postgres");
  }

  modal.classList.add("open");
}

function closeConnModal() {
  document.getElementById("connModal").classList.remove("open");
}

function getFormData() {
  const dbType = document.getElementById("formDbType").value;
  const isGcp = dbType === "datastore" || dbType === "featurestore";
  const gcpProject = document.getElementById("formGcpProject") ? document.getElementById("formGcpProject").value.trim() : "";

  return {
    id: document.getElementById("formConnId").value || undefined,
    name: document.getElementById("formConnName").value.trim(),
    db_type: dbType,
    host: isGcp ? (dbType === "datastore" ? "datastore.googleapis.com" : "aiplatform.googleapis.com") : document.getElementById("formHost").value.trim(),
    port: isGcp ? 443 : parseInt(document.getElementById("formPort").value || 5432, 10),
    database: isGcp ? (gcpProject || "gcp-project") : document.getElementById("formDatabase").value.trim(),
    user: isGcp ? "service-account" : document.getElementById("formUser").value.trim(),
    password: isGcp ? "" : document.getElementById("formPassword").value,
    client_encoding: document.getElementById("formEncoding")?.value.trim() || undefined,
    project_id: gcpProject || undefined,
    credentials_path: document.getElementById("formGcpKeyPath")?.value.trim() || undefined,
    location: document.getElementById("formGcpLocation")?.value.trim() || "us-central1",
    database_id: document.getElementById("formGcpDatastoreDb")?.value.trim() || "(default)"
  };
}

async function testConnectionFromModal() {
  const data = getFormData();
  const testBox = document.getElementById("testResultBox");
  testBox.style.display = "block";
  testBox.style.background = "var(--bg-input)";
  testBox.style.color = "var(--text-main)";
  testBox.innerHTML = `<span class="spinner" style="width:12px;height:12px"></span> Testando conexão...`;

  try {
    const res = await fetch("/api/test-connection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    const result = await res.json();
    if (result.success) {
      testBox.style.background = "rgba(16, 185, 129, 0.15)";
      testBox.style.color = "#34d399";
      testBox.innerHTML = `✓ ${result.message}<br><small>${result.version}</small>`;
    } else {
      testBox.style.background = "rgba(239, 68, 68, 0.15)";
      testBox.style.color = "#f87171";
      testBox.innerHTML = `✕ ${result.message || result.error}`;
    }
  } catch (err) {
    testBox.style.background = "rgba(239, 68, 68, 0.15)";
    testBox.style.color = "#f87171";
    testBox.innerHTML = `✕ Erro de comunicação: ${err.message}`;
  }
}

async function saveConnectionFromModal() {
  const data = getFormData();
  try {
    const res = await fetch("/api/connections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    const result = await res.json();
    if (result.success) {
      closeConnModal();
      await loadConnections();
      setActiveConnection(result.connection.id);
    }
  } catch (err) {
    alert("Erro ao salvar conexão: " + err.message);
  }
}

// Utilitários
function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

