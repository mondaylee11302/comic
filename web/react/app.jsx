const { useEffect, useMemo, useState } = React;

const STEP_ORDER = ["upload", "extract", "select", "generate"];
const DEFAULT_OUT_DIR = "/Users/lishuai/Documents/python/Picslit2/output";
const DEFAULT_DEBUG_DIR = "/Users/lishuai/Documents/python/Picslit2/output/debug";
const DEFAULT_MODEL_ENDPOINT = "doubao-seed-1-8-251228";

function fileUrl(path) {
  return path ? `/api/file?path=${encodeURIComponent(path)}` : "";
}

async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return await res.json();
}

async function apiPost(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return await res.json();
}

function Stepper({ currentStep, uploaded, storyboard, selectedPanel, onJump }) {
  const done = {
    upload: Boolean(uploaded?.stored_path),
    extract: Boolean(storyboard?.panel_count),
    select: Boolean(selectedPanel?.panel_id),
    generate: false,
  };
  const activeIndex = STEP_ORDER.indexOf(currentStep);

  const labels = {
    upload: "上传PSD",
    extract: "提取分镜",
    select: "选择内容",
    generate: "生成脚本",
  };

  return (
    <div className="stepper">
      {STEP_ORDER.map((k, idx) => (
        <button
          type="button"
          key={k}
          className={`step ${currentStep === k ? "active" : ""} ${done[k] ? "done" : ""}`}
          onClick={() => idx <= activeIndex && onJump(k)}
        >
          <span className="num">{done[k] ? "✓" : idx + 1}</span>
          <span>{labels[k]}</span>
        </button>
      ))}
    </div>
  );
}

function WorkflowPage() {
  const [currentStep, setCurrentStep] = useState("upload");
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploaded, setUploaded] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);

  const [outDir, setOutDir] = useState(DEFAULT_OUT_DIR);
  const [debugDir, setDebugDir] = useState(DEFAULT_DEBUG_DIR);
  const [prefix, setPrefix] = useState("storyboard_001");
  const [strictOcr, setStrictOcr] = useState(true);
  const [splitMode, setSplitMode] = useState("bands");
  const [reuseCache, setReuseCache] = useState(true);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [heartbeatSec, setHeartbeatSec] = useState(8);
  const [verbose, setVerbose] = useState(true);

  const [storyboard, setStoryboard] = useState(null);
  const [statusText, setStatusText] = useState("等待上传PSD文件。");
  const [selectedPanel, setSelectedPanel] = useState(null);
  const [panelTexts, setPanelTexts] = useState([]);
  const [selectedTextIds, setSelectedTextIds] = useState([]);

  const [goal, setGoal] = useState("保留原文语义并增强戏剧性，输出可直接给创作团队使用的分镜脚本");
  const [modelEndpoint, setModelEndpoint] = useState(DEFAULT_MODEL_ENDPOINT);
  const [modelApiKey, setModelApiKey] = useState("");
  const [modelBaseUrl, setModelBaseUrl] = useState("https://ark.cn-beijing.volces.com/api/v3");
  const [temperature, setTemperature] = useState(0.35);
  const [maxTokens, setMaxTokens] = useState(1200);
  const [requestTimeout, setRequestTimeout] = useState(60);
  const [modelRetries, setModelRetries] = useState(2);
  const [scriptHeartbeat, setScriptHeartbeat] = useState(8);
  const [allowFallback, setAllowFallback] = useState(true);

  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");

  async function uploadPsd() {
    if (!selectedFile) {
      setErrorMsg("请先选择PSD/PSB文件。");
      return;
    }
    setErrorMsg("");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", selectedFile);
      fd.append("out_dir", outDir);
      const res = await fetch("/api/upload-psd", { method: "POST", body: fd });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = await res.json();
      setUploaded(data);
      setStatusText(`上传成功: ${data.stored_path}`);
      if (!prefix.trim()) {
        const name = (data.file_name || "storyboard").replace(/\.(psd|psb)$/i, "");
        setPrefix(name || "storyboard_001");
      }
      setCurrentStep("extract");
    } catch (err) {
      setErrorMsg(`上传失败: ${err.message}`);
    } finally {
      setUploading(false);
    }
  }

  async function loadPanel(panelId, sb = storyboard) {
    if (!sb || !panelId) return;
    setErrorMsg("");
    try {
      const qs = new URLSearchParams({
        out_dir: sb.out_dir,
        prefix: sb.prefix,
        panel_id: panelId,
      });
      const data = await apiGet(`/api/panel/details?${qs.toString()}`);
      setSelectedPanel(data.panel);
      setPanelTexts(data.texts || []);
      setSelectedTextIds((data.texts || []).map((x) => x.text_id).filter(Boolean));
      setCurrentStep("select");
    } catch (err) {
      setErrorMsg(`加载分镜失败: ${err.message}`);
    }
  }

  async function runStoryboard() {
    if (!uploaded?.stored_path) {
      setErrorMsg("请先上传PSD文件。");
      return;
    }
    setErrorMsg("");
    setRunning(true);
    setGenerated(null);
    try {
      const payload = {
        image_path: uploaded.stored_path,
        prefix,
        out_dir: outDir,
        debug_dir: debugDir,
        strict_ocr: strictOcr,
        split_mode: splitMode,
        reuse_cache: reuseCache,
        force_reprocess: forceReprocess,
        heartbeat_sec: Number(heartbeatSec),
        verbose,
      };
      const data = await apiPost("/api/storyboard/run", payload);
      setStoryboard(data);
      setStatusText(`提取完成：共 ${data.panel_count} 个分镜，文本 ${data.text_count} 条。`);
      if (data.panels && data.panels.length > 0) {
        await loadPanel(data.panels[0].panel_id, data);
      }
    } catch (err) {
      setErrorMsg(`提取失败: ${err.message}`);
    } finally {
      setRunning(false);
    }
  }

  async function generateScript() {
    if (!storyboard || !selectedPanel) {
      setErrorMsg("请先选择分镜。");
      return;
    }
    setGenerating(true);
    setErrorMsg("");
    try {
      const payload = {
        out_dir: storyboard.out_dir,
        prefix: storyboard.prefix,
        panel_id: selectedPanel.panel_id,
        panel_image_path: selectedPanel.image_path,
        panel_text_path: selectedPanel.txt_path,
        selected_text_ids: selectedTextIds,
        goal,
        temperature: Number(temperature),
        max_tokens: Number(maxTokens),
        request_timeout_sec: Number(requestTimeout),
        model_retries: Number(modelRetries),
        heartbeat_sec: Number(scriptHeartbeat),
        allow_local_fallback: allowFallback,
        model_endpoint: modelEndpoint,
        api_key: modelApiKey,
        base_url: modelBaseUrl,
        verbose,
      };
      const data = await apiPost("/api/script/generate", payload);
      setGenerated(data);
      setCurrentStep("generate");
    } catch (err) {
      setErrorMsg(`生成失败: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  }

  const selectedTextCount = selectedTextIds.length;

  return (
    <div>
      <div className="card">
        <Stepper
          currentStep={currentStep}
          uploaded={uploaded}
          storyboard={storyboard}
          selectedPanel={selectedPanel}
          onJump={setCurrentStep}
        />
      </div>

      <div className="card">
        <div className="status">{statusText}</div>
        {errorMsg ? <div className="status" style={{ color: "#cf3f49", marginTop: 8 }}>{errorMsg}</div> : null}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>步骤1：上传 PSD/PSB</h3>
        <div className="row-wrap">
          <div style={{ minWidth: 280, flex: 1 }}>
            <label className="field-label">选择文件</label>
            <input
              type="file"
              accept=".psd,.psb"
              onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
            />
          </div>
          <div style={{ minWidth: 180 }}>
            <label className="field-label">动作</label>
            <button type="button" className="btn" onClick={uploadPsd} disabled={uploading || !selectedFile}>
              {uploading ? "上传中..." : "上传文件"}
            </button>
          </div>
        </div>
        <div style={{ marginTop: 12 }} className="preview-box">
          {uploaded?.preview_path ? (
            <img src={fileUrl(uploaded.preview_path)} alt="PSD Preview" />
          ) : (
            <div style={{ color: "#6b7386", fontSize: 13, textAlign: "center", padding: 20 }}>
              上传后会显示PSD预览（若可解析）
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>步骤2：提取净图、分镜、文字</h3>
        <div className="row-wrap">
          <div style={{ minWidth: 220, flex: 1 }}>
            <label className="field-label">Prefix</label>
            <input value={prefix} onChange={(e) => setPrefix(e.target.value)} />
          </div>
          <div style={{ minWidth: 280, flex: 1 }}>
            <label className="field-label">输出目录</label>
            <input value={outDir} onChange={(e) => setOutDir(e.target.value)} />
          </div>
          <div style={{ minWidth: 280, flex: 1 }}>
            <label className="field-label">调试目录</label>
            <input value={debugDir} onChange={(e) => setDebugDir(e.target.value)} />
          </div>
        </div>
        <div className="row-wrap" style={{ marginTop: 10 }}>
          <label className="badge"><input type="checkbox" checked={strictOcr} onChange={(e) => setStrictOcr(e.target.checked)} /> 严格OCR</label>
          <label className="badge"><input type="checkbox" checked={reuseCache} onChange={(e) => setReuseCache(e.target.checked)} /> 复用缓存</label>
          <label className="badge"><input type="checkbox" checked={forceReprocess} onChange={(e) => setForceReprocess(e.target.checked)} /> 强制重跑</label>
          <label className="badge">split_mode:
            <select style={{ marginLeft: 6, width: 90 }} value={splitMode} onChange={(e) => setSplitMode(e.target.value)}>
              <option value="bands">bands</option>
              <option value="stage2">stage2</option>
            </select>
          </label>
          <label className="badge">heartbeat:
            <input style={{ marginLeft: 6, width: 64 }} type="number" value={heartbeatSec} onChange={(e) => setHeartbeatSec(e.target.value)} />
          </label>
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="button" className="btn" onClick={runStoryboard} disabled={running || !uploaded?.stored_path}>
            {running ? "处理中..." : "开始提取"}
          </button>
        </div>
        <div style={{ marginTop: 12 }} className="preview-box">
          {storyboard?.clean_image_path ? (
            <img src={fileUrl(storyboard.clean_image_path)} alt="Clean Art" />
          ) : (
            <div style={{ color: "#6b7386", fontSize: 13 }}>提取完成后会显示纯净画面</div>
          )}
        </div>
        {storyboard?.logs?.length ? <div className="log-box">{storyboard.logs.join("\n")}</div> : null}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>步骤3：选择分镜图片与文字</h3>
        <div className="panel-layout">
          <div className="panel-list">
            {(storyboard?.panels || []).map((p) => (
              <div
                key={p.panel_id}
                className={`panel-item ${selectedPanel?.panel_id === p.panel_id ? "active" : ""}`}
                onClick={() => loadPanel(p.panel_id)}
              >
                <img src={fileUrl(p.image_path)} alt={p.panel_id} />
                <div className="meta">{p.panel_id} | 文本 {p.text_count} 条</div>
              </div>
            ))}
          </div>
          <div>
            <div className="row-wrap" style={{ marginBottom: 10 }}>
              <button
                type="button"
                className="btn secondary"
                onClick={() => setSelectedTextIds(panelTexts.map((x) => x.text_id).filter(Boolean))}
                disabled={!panelTexts.length}
              >
                文本全选
              </button>
              <button
                type="button"
                className="btn secondary"
                onClick={() => setSelectedTextIds([])}
                disabled={!panelTexts.length}
              >
                清空选择
              </button>
              <span className="badge">已选 {selectedTextCount} 条</span>
            </div>

            <div className="text-list">
              {panelTexts.length === 0 ? <div style={{ color: "#6a7386", fontSize: 13 }}>当前分镜暂无文本。</div> : null}
              {panelTexts.map((t) => (
                <div className="text-row" key={t.text_id}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={selectedTextIds.includes(t.text_id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedTextIds((prev) => Array.from(new Set([...prev, t.text_id])));
                        } else {
                          setSelectedTextIds((prev) => prev.filter((x) => x !== t.text_id));
                        }
                      }}
                    />
                    <strong style={{ fontSize: 12 }}>{t.text_id}</strong>
                    <span className="badge">score {t.assignment_score || "-"}</span>
                  </label>
                  <p>{t.text || ""}</p>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 10 }}>
              <label className="field-label">可选提示词</label>
              <textarea value={goal} onChange={(e) => setGoal(e.target.value)} />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>步骤4：生成当前分镜脚本（豆包 1.8 多模态）</h3>
        <div className="row-wrap">
          <div style={{ minWidth: 280, flex: 1 }}>
            <label className="field-label">MODEL_ENDPOINT</label>
            <input value={modelEndpoint} onChange={(e) => setModelEndpoint(e.target.value)} />
          </div>
          <div style={{ minWidth: 280, flex: 1 }}>
            <label className="field-label">API_KEY（可空）</label>
            <input type="password" value={modelApiKey} onChange={(e) => setModelApiKey(e.target.value)} />
          </div>
          <div style={{ minWidth: 280, flex: 1 }}>
            <label className="field-label">BASE_URL</label>
            <input value={modelBaseUrl} onChange={(e) => setModelBaseUrl(e.target.value)} />
          </div>
        </div>
        <div className="row-wrap" style={{ marginTop: 10 }}>
          <label className="badge">temperature <input type="number" step="0.05" style={{ marginLeft: 6, width: 70 }} value={temperature} onChange={(e) => setTemperature(e.target.value)} /></label>
          <label className="badge">max_tokens <input type="number" style={{ marginLeft: 6, width: 82 }} value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} /></label>
          <label className="badge">timeout <input type="number" style={{ marginLeft: 6, width: 64 }} value={requestTimeout} onChange={(e) => setRequestTimeout(e.target.value)} /></label>
          <label className="badge">retries <input type="number" style={{ marginLeft: 6, width: 52 }} value={modelRetries} onChange={(e) => setModelRetries(e.target.value)} /></label>
          <label className="badge"><input type="checkbox" checked={allowFallback} onChange={(e) => setAllowFallback(e.target.checked)} /> 允许本地兜底</label>
        </div>
        <div style={{ marginTop: 12 }}>
          <button
            type="button"
            className="btn success"
            onClick={generateScript}
            disabled={generating || !selectedPanel?.panel_id}
          >
            {generating ? "生成中..." : "生成分镜脚本"}
          </button>
        </div>

        {generated ? (
          <div style={{ marginTop: 14 }}>
            <div className="status">
              backend: <b>{generated.backend}</b>
              {generated.script_json_path ? <> | json: <code>{generated.script_json_path}</code></> : null}
              {generated.script_md_path ? <> | md: <code>{generated.script_md_path}</code></> : null}
            </div>
            {generated.script_md_path ? (
              <div style={{ marginTop: 8 }}>
                <a className="btn secondary" href={fileUrl(generated.script_md_path)} target="_blank" rel="noreferrer">打开脚本文件</a>
              </div>
            ) : null}
            <pre className="log-box" style={{ minHeight: 180 }}>{generated.script_markdown || JSON.stringify(generated.script, null, 2)}</pre>
            {generated.logs?.length ? <div className="log-box">{generated.logs.join("\n")}</div> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AssetsPage() {
  const [outDir, setOutDir] = useState(DEFAULT_OUT_DIR);
  const [prefixFilter, setPrefixFilter] = useState("");
  const [keyword, setKeyword] = useState("");
  const [assetType, setAssetType] = useState("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState({ counts: {}, items: [], gallery: [], script_paths: [], prefix_count: 0 });
  const [scriptPath, setScriptPath] = useState("");
  const [scriptPreview, setScriptPreview] = useState("");

  async function refreshAssets() {
    setLoading(true);
    setError("");
    try {
      const qs = new URLSearchParams({
        out_dir: outDir,
        prefix_filter: prefixFilter,
        keyword,
        asset_type: assetType,
      });
      const res = await apiGet(`/api/assets/list?${qs.toString()}`);
      setData(res);
      const firstScript = (res.script_paths || [])[0] || "";
      setScriptPath(firstScript);
      if (firstScript) {
        const p = await apiGet(`/api/script/preview?path=${encodeURIComponent(firstScript)}`);
        setScriptPreview(p.content || "");
      } else {
        setScriptPreview("");
      }
    } catch (err) {
      setError(`资产扫描失败: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function loadScriptPreview(path) {
    setScriptPath(path);
    if (!path) {
      setScriptPreview("");
      return;
    }
    try {
      const p = await apiGet(`/api/script/preview?path=${encodeURIComponent(path)}`);
      setScriptPreview(p.content || "");
    } catch (err) {
      setError(`读取脚本失败: ${err.message}`);
    }
  }

  useEffect(() => {
    refreshAssets();
  }, []);

  const counts = data.counts || {};

  return (
    <div>
      <div className="card">
        <div className="row-wrap">
          <div style={{ minWidth: 260, flex: 1 }}>
            <label className="field-label">输出目录</label>
            <input value={outDir} onChange={(e) => setOutDir(e.target.value)} />
          </div>
          <div style={{ minWidth: 180 }}>
            <label className="field-label">Prefix过滤</label>
            <input value={prefixFilter} onChange={(e) => setPrefixFilter(e.target.value)} />
          </div>
          <div style={{ minWidth: 180 }}>
            <label className="field-label">关键字</label>
            <input value={keyword} onChange={(e) => setKeyword(e.target.value)} />
          </div>
          <div style={{ minWidth: 150 }}>
            <label className="field-label">类型</label>
            <select value={assetType} onChange={(e) => setAssetType(e.target.value)}>
              <option value="all">全部</option>
              <option value="psd">PSD</option>
              <option value="frame">分镜PNG</option>
              <option value="text">分镜文本</option>
              <option value="script">脚本</option>
            </select>
          </div>
          <div style={{ minWidth: 120 }}>
            <label className="field-label">动作</label>
            <button type="button" className="btn" onClick={refreshAssets} disabled={loading}>{loading ? "刷新中..." : "刷新"}</button>
          </div>
        </div>
        <div className="row-wrap" style={{ marginTop: 10 }}>
          <span className="badge">PSD: {counts.psd || 0}</span>
          <span className="badge">分镜PNG: {counts.frame || 0}</span>
          <span className="badge">分镜文本: {counts.text || 0}</span>
          <span className="badge">脚本: {counts.script || 0}</span>
          <span className="badge">Prefix: {data.prefix_count || 0}</span>
        </div>
        {error ? <div className="status" style={{ color: "#cf3f49", marginTop: 10 }}>{error}</div> : null}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>分镜图集</h3>
        <div className="assets-grid">
          {(data.gallery || []).map((g, idx) => (
            <div className="asset-card" key={`${g.path}_${idx}`}>
              <img src={fileUrl(g.path)} alt={g.label} />
              <div className="body">
                <div className="name">{g.label}</div>
                <div className="meta">{g.path}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>资产列表</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>type</th>
                <th>prefix</th>
                <th>name</th>
                <th>size</th>
                <th>mtime</th>
                <th>path</th>
              </tr>
            </thead>
            <tbody>
              {(data.items || []).map((row, idx) => (
                <tr key={`${row.path}_${idx}`}>
                  <td>{row.type}</td>
                  <td>{row.prefix}</td>
                  <td>{row.name}</td>
                  <td>{row.size}</td>
                  <td>{row.mtime}</td>
                  <td style={{ maxWidth: 560, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>脚本预览</h3>
        <div className="row-wrap">
          <div style={{ minWidth: 420, flex: 1 }}>
            <label className="field-label">脚本文件</label>
            <select value={scriptPath} onChange={(e) => loadScriptPreview(e.target.value)}>
              <option value="">请选择脚本</option>
              {(data.script_paths || []).map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div style={{ minWidth: 160 }}>
            <label className="field-label">动作</label>
            <a className="btn secondary" href={scriptPath ? fileUrl(scriptPath) : "#"} target="_blank" rel="noreferrer">打开文件</a>
          </div>
        </div>
        <pre className="log-box" style={{ minHeight: 220 }}>{scriptPreview || "暂无脚本内容"}</pre>
      </div>
    </div>
  );
}

function App() {
  const [page, setPage] = useState("workflow");

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>Storyboard Generator 工作台（React）</h1>
          <p>上传PSD -> 提取净图与分镜 -> 选择分镜与文字 -> 生成分镜脚本，同时支持静态资产管理。</p>
        </div>
        <div className="nav-btns">
          <button type="button" className={`nav-btn ${page === "workflow" ? "active" : ""}`} onClick={() => setPage("workflow")}>工作流程</button>
          <button type="button" className={`nav-btn ${page === "assets" ? "active" : ""}`} onClick={() => setPage("assets")}>资产管理</button>
        </div>
      </header>

      {page === "workflow" ? <WorkflowPage /> : <AssetsPage />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
