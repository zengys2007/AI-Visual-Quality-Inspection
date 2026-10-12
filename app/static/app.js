(() => {
  "use strict";

  const IMAGE_EXT = /\.(jpe?g|png|bmp|webp)$/i;
  /** 赛题二电池包：仅允许这两类；忽略窗帘布 Hole / Ink / Broken_Filament */
  const CLASS_CRACK = "Surface_Crack";
  const CLASS_OK = "Ok";
  const CSV_HEADER =
    "image_id,class_name,confidence,x_min,y_min,x_max,y_max,inference_time_ms";
  const EXPORT_PREFIX = "兴欣_检测结果";
  const LS_LINE = "qi_export_line";
  const LS_SHIFT = "qi_export_shift";
  const LS_DETAIL = "qi_export_detail";
  /** 仅在用户点击日/夜切换时写入；缺省则跟随系统 */
  const LS_THEME = "qi_theme_user";
  const WHEEL_ITEM_H = 36;
  /** 默认置信度阈值，与 src/predict.py 的 CONF 保持一致 */
  const DEFAULT_CONF = 0.223;

  /** @type {{ id: string, name: string, url: string, path?: string, width: number, height: number, records: object[] | null, verdict: 'pending'|'ok'|'ng', inferenceMs: number | null }[]} */
  let images = [];
  let activeId = null;
  /** @type {Set<string>} 导出用多选集合（与预览 activeId 独立） */
  let selectedIds = new Set();
  let busy = false;
  let engineReady = false;
  let weightsLabel = "";
  let choosingWeights = false;
  /** @type {number | null} */
  let detectConf = null;

  const els = {
    fileInput: document.getElementById("fileInput"),
    folderInput: document.getElementById("folderInput"),
    clearBtn: document.getElementById("clearBtn"),
    selectAllBtn: document.getElementById("selectAllBtn"),
    detectOneBtn: document.getElementById("detectOneBtn"),
    detectAllBtn: document.getElementById("detectAllBtn"),
    exportBtn: document.getElementById("exportBtn"),
    gallery: document.getElementById("gallery"),
    galleryEmpty: document.getElementById("galleryEmpty"),
    imageCount: document.getElementById("imageCount"),
    selectedInfo: document.getElementById("selectedInfo"),
    canvas: document.getElementById("previewCanvas"),
    placeholder: document.getElementById("viewerPlaceholder"),
    currentName: document.getElementById("currentName"),
    currentVerdict: document.getElementById("currentVerdict"),
    currentTime: document.getElementById("currentTime"),
    resultBody: document.getElementById("resultBody"),
    resultCount: document.getElementById("resultCount"),
    sessionInfo: document.getElementById("sessionInfo"),
    statusMsg: document.getElementById("statusMsg"),
    connStatus: document.getElementById("connStatus"),
    expandBtn: document.getElementById("expandBtn"),
    compareModal: document.getElementById("compareModal"),
    compareBackdrop: document.getElementById("compareBackdrop"),
    compareClose: document.getElementById("compareClose"),
    compareSub: document.getElementById("compareSub"),
    compareBefore: document.getElementById("compareBefore"),
    compareAfter: document.getElementById("compareAfter"),
    compareAfterEmpty: document.getElementById("compareAfterEmpty"),
    exportModal: document.getElementById("exportModal"),
    exportBackdrop: document.getElementById("exportBackdrop"),
    exportClose: document.getElementById("exportClose"),
    exportCancel: document.getElementById("exportCancel"),
    exportForm: document.getElementById("exportForm"),
    exportDetail: document.getElementById("exportDetail"),
    exportDetailFields: document.getElementById("exportDetailFields"),
    exportLine: document.getElementById("exportLine"),
    exportShift: document.getElementById("exportShift"),
    exportDate: document.getElementById("exportDate"),
    exportPreview: document.getElementById("exportPreview"),
    wheelYear: document.getElementById("wheelYear"),
    wheelMonth: document.getElementById("wheelMonth"),
    wheelDay: document.getElementById("wheelDay"),
    themeDayBtn: document.getElementById("themeDayBtn"),
    themeNightBtn: document.getElementById("themeNightBtn"),
    alertModal: document.getElementById("alertModal"),
    alertBackdrop: document.getElementById("alertBackdrop"),
    alertClose: document.getElementById("alertClose"),
    alertOk: document.getElementById("alertOk"),
    alertTitle: document.getElementById("alertTitle"),
    alertMessage: document.getElementById("alertMessage"),
    confCurrent: document.getElementById("confCurrent"),
    statTotal: document.getElementById("statTotal"),
    statNg: document.getElementById("statNg"),
    statOk: document.getElementById("statOk"),
  };

  /** @type {{ csv: string, imageCount: number, rowCount: number } | null} */
  let pendingExport = null;
  let wheelSyncing = false;

  const ctx = els.canvas.getContext("2d");
  const compareCtx = els.compareAfter ? els.compareAfter.getContext("2d") : null;

  function setStatus(msg) {
    els.statusMsg.textContent = msg;
  }

  function setConnStatus(text, kind) {
    if (!els.connStatus) return;
    els.connStatus.textContent = text;
    els.connStatus.title =
      kind === "ready"
        ? `当前权重：${text}（点击可更换）`
        : "点击选择 YOLO 权重文件 (.pt)";
    els.connStatus.className = `status-pill${kind ? ` ${kind}` : " pick"}`;
    els.connStatus.disabled = choosingWeights || busy;
  }

  function showAlert(title, message) {
    if (!els.alertModal) {
      window.alert(message);
      return;
    }
    if (els.alertTitle) els.alertTitle.textContent = title || "提示";
    if (els.alertMessage) els.alertMessage.textContent = message || "";
    els.alertModal.hidden = false;
  }

  function closeAlert() {
    if (els.alertModal) els.alertModal.hidden = true;
  }

  function weightsStatusText() {
    return weightsLabel ? `YOLO · ${weightsLabel}` : "选择权重文件";
  }

  async function chooseWeightsFile() {
    if (choosingWeights || busy) return;
    const api = pyApi();
    if (!api || typeof api.choose_weights !== "function") {
      setStatus("请通过 app/desktop.py 启动桌面应用以选择权重");
      setConnStatus("未连接后端", "error");
      return;
    }

    choosingWeights = true;
    clearConfField();
    setConnStatus("选择中…", "busy");
    setButtons();
    try {
      const res = await api.choose_weights();
      if (!res || res.cancelled) {
        setConnStatus(
          engineReady ? weightsStatusText() : "选择权重文件",
          engineReady ? "ready" : "pick"
        );
        if (!engineReady) {
          clearConfField();
        }
        setStatus(engineReady ? "已取消更换权重" : "请选择 .pt 权重文件后再检测");
        return;
      }
      if (res.invalid_type) {
        showAlert(
          "文件类型不符",
          res.error || "所选文件不是 .pt 权重，请重新选择。"
        );
        setConnStatus(
          engineReady ? weightsStatusText() : "选择权重文件",
          engineReady ? "ready" : "pick"
        );
        setStatus("权重文件类型不符，请选择 .pt");
        return;
      }
      if (!res.ok) {
        engineReady = false;
        weightsLabel = "";
        setConnStatus("选择权重文件", "error");
        clearConfField();
        setStatus(res.error || "权重加载失败");
        showAlert("权重加载失败", res.error || "无法加载所选权重文件。");
        return;
      }
      onEngineReady(res);
      choosingWeights = false;
      if (els.connStatus) els.connStatus.disabled = busy;
      setButtons();
    } catch (err) {
      setConnStatus(
        engineReady ? weightsStatusText() : "选择权重文件",
        engineReady ? "ready" : "error"
      );
      setStatus(err && err.message ? err.message : String(err));
    } finally {
      choosingWeights = false;
      if (els.connStatus) els.connStatus.disabled = busy;
      setButtons();
    }
  }

  function activeImage() {
    return images.find((img) => img.id === activeId) || null;
  }

  function loadImageMeta(file, url, path) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () =>
        resolve({
          id: `${file.name}_${file.size}_${file.lastModified}`,
          name: file.name,
          url,
          path: path || undefined,
          width: img.naturalWidth,
          height: img.naturalHeight,
          records: null,
          verdict: "pending",
          inferenceMs: null,
        });
      img.onerror = () => reject(new Error(`无法读取图像: ${file.name}`));
      img.src = url;
    });
  }

  function blobUrlToDataUrl(url) {
    return fetch(url)
      .then((res) => res.blob())
      .then(
        (blob) =>
          new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error("读取图像失败"));
            reader.readAsDataURL(blob);
          })
      );
  }

  function pyApi() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function formatConf(value) {
    return Number(value).toFixed(3);
  }

  function clearConfField() {
    detectConf = null;
    if (els.confCurrent) els.confCurrent.value = "";
  }

  function refreshConfDisplay() {
    if (!els.confCurrent) return;
    if (detectConf == null || !Number.isFinite(detectConf)) {
      els.confCurrent.value = "";
      return;
    }
    if (document.activeElement !== els.confCurrent) {
      els.confCurrent.value = formatConf(detectConf);
    }
  }

  function applyConfInput({ silent = false } = {}) {
    if (!els.confCurrent) return false;
    const raw = String(els.confCurrent.value || "").trim();
    if (!raw) {
      if (!silent) {
        showAlert("置信度为空", "请输入 0 ~ 1 之间的数字（默认 0.223）。");
        setStatus("置信度为空，请先填写");
      }
      return false;
    }
    const v = Number(raw);
    if (!Number.isFinite(v) || v < 0 || v > 1) {
      if (!silent) {
        showAlert("置信度无效", "请输入 0 ~ 1 之间的数字（例如 0.223）。");
        setStatus("置信度无效");
      }
      refreshConfDisplay();
      return false;
    }
    detectConf = Math.round(v * 1000) / 1000;
    refreshConfDisplay();
    const api = pyApi();
    if (api && typeof api.set_conf === "function") {
      api.set_conf(detectConf).catch(() => {});
    }
    if (!silent) {
      setStatus(`置信度已更新为 ${formatConf(detectConf)}`);
    }
    return true;
  }

  async function yoloDetect(image) {
    const api = pyApi();
    if (!api || typeof api.detect_image !== "function") {
      throw new Error("请通过 app/desktop.py 启动桌面应用以使用 YOLO 检测");
    }
    if (!applyConfInput({ silent: true }) || detectConf == null) {
      throw new Error("请先填写置信度（0 ~ 1，默认 0.223）");
    }
    const payload = { name: image.name, conf: detectConf };
    if (image.path) {
      payload.path = image.path;
    } else {
      payload.dataUrl = await blobUrlToDataUrl(image.url);
    }
    const res = await api.detect_image(payload);
    if (!res || !res.ok) {
      throw new Error((res && res.error) || "检测失败");
    }
    return res;
  }

  function onEngineReady(status) {
    if (status && status.ok) {
      engineReady = true;
      weightsLabel = status.name || status.weights_name || "weights.pt";
      if (!status.name && status.weights) {
        const parts = String(status.weights).split(/[/\\]/);
        weightsLabel = parts[parts.length - 1] || weightsLabel;
      }
      setConnStatus(weightsStatusText(), "ready");
      // 无推荐功能：填入默认置信度（可手动修改）
      detectConf = DEFAULT_CONF;
      refreshConfDisplay();
      const api = pyApi();
      if (api && typeof api.set_conf === "function") {
        api.set_conf(DEFAULT_CONF).catch(() => {});
      }
      setStatus(`模型已加载 · ${weightsLabel}`);
    } else if (status && status.need_weights) {
      engineReady = false;
      weightsLabel = "";
      setConnStatus("选择权重文件", "pick");
      clearConfField();
      setStatus("请先点击右上角选择 .pt 权重文件");
    } else {
      engineReady = false;
      weightsLabel = "";
      const err = (status && status.error) || "模型未就绪";
      setConnStatus("选择权重文件", "error");
      clearConfField();
      setStatus(err);
    }
    setButtons();
  }

  window.onEngineReady = onEngineReady;

  async function commitImported(items) {
    if (!items.length) {
      setStatus("没有新增图像（可能与已导入文件重名）");
      return;
    }
    if (!activeId) activeId = items[0].id;
    renderAll();
    setStatus(`已导入 ${items.length} 张图像`);
  }

  async function importFiles(fileList) {
    const files = Array.from(fileList || []).filter((f) => IMAGE_EXT.test(f.name));
    if (!files.length) {
      setStatus("未找到可导入的图像文件");
      return;
    }

    const existing = new Set(images.map((i) => i.name));
    const added = [];

    for (const file of files) {
      if (existing.has(file.name)) continue;
      const url = URL.createObjectURL(file);
      try {
        const item = await loadImageMeta(file, url);
        images.push(item);
        existing.add(file.name);
        added.push(item);
      } catch {
        URL.revokeObjectURL(url);
      }
    }

    await commitImported(added);
  }

  /** 供 desktop.py 拖放桥接：接收 { name, size, lastModified, dataUrl } */
  async function importDroppedImages(payload) {
    const list = Array.isArray(payload) ? payload : [];
    const entries = list.filter(
      (item) => item && IMAGE_EXT.test(item.name || "") && item.dataUrl
    );
    if (!entries.length) {
      setStatus("未找到可导入的图像文件");
      return;
    }

    const existing = new Set(images.map((i) => i.name));
    const added = [];

    for (const entry of entries) {
      if (existing.has(entry.name)) continue;
      try {
        const item = await loadImageMeta(
          {
            name: entry.name,
            size: entry.size || 0,
            lastModified: entry.lastModified || Date.now(),
          },
          entry.dataUrl,
          entry.path || undefined
        );
        images.push(item);
        existing.add(entry.name);
        added.push(item);
      } catch {
        /* skip unreadable */
      }
    }

    await commitImported(added);
  }

  window.importDroppedImages = importDroppedImages;
  window.setStatusMessage = setStatus;
  window.importImageFiles = importFiles;

  function revokeImageUrl(url) {
    if (url && String(url).startsWith("blob:")) URL.revokeObjectURL(url);
  }

  function selectedImages() {
    return images.filter((img) => selectedIds.has(img.id));
  }

  function pruneSelection() {
    const valid = new Set(images.map((img) => img.id));
    selectedIds = new Set([...selectedIds].filter((id) => valid.has(id)));
  }

  function allSelected() {
    return images.length > 0 && images.every((img) => selectedIds.has(img.id));
  }

  function selectAllImages() {
    if (!images.length) return;
    if (allSelected()) {
      selectedIds.clear();
      setStatus("已取消全选");
    } else {
      selectedIds = new Set(images.map((img) => img.id));
      setStatus(`已全选 ${images.length} 张图像`);
    }
    renderAll();
  }

  function toggleSelect(id) {
    if (selectedIds.has(id)) selectedIds.delete(id);
    else selectedIds.add(id);
    renderAll();
  }

  function clearSelected() {
    pruneSelection();
    const chosen = selectedImages();
    if (!chosen.length) {
      setStatus("请先勾选要清空的图像，或点击「全选」");
      return;
    }

    const removeIds = new Set(chosen.map((img) => img.id));
    const removedCount = removeIds.size;

    images.forEach((img) => {
      if (removeIds.has(img.id)) revokeImageUrl(img.url);
    });
    images = images.filter((img) => !removeIds.has(img.id));
    selectedIds.clear();

    if (!images.length) {
      activeId = null;
    } else if (!images.some((img) => img.id === activeId)) {
      activeId = images[0].id;
    }

    renderAll();
    setStatus(
      images.length
        ? `已清空选中 ${removedCount} 张，剩余 ${images.length} 张`
        : `已清空选中 ${removedCount} 张`
    );
  }

  function removeImage(id) {
    if (busy) return;
    const idx = images.findIndex((img) => img.id === id);
    if (idx < 0) return;

    const [removed] = images.splice(idx, 1);
    revokeImageUrl(removed.url);
    selectedIds.delete(id);

    if (activeId === id) {
      const next = images[idx] || images[idx - 1] || null;
      activeId = next ? next.id : null;
    }

    renderAll();
    setStatus(`已删除: ${removed.name}`);
  }

  async function runDetect(targets) {
    if (busy || !targets.length) return;
    const api = pyApi();
    if (!api || typeof api.detect_image !== "function") {
      setStatus("请通过 app/desktop.py 启动桌面应用以使用 YOLO 检测");
      setConnStatus("未连接后端", "error");
      return;
    }
    if (!engineReady) {
      setStatus("请先点击右上角选择 .pt 权重文件");
      setConnStatus("选择权重文件", "pick");
      return;
    }
    if (!applyConfInput({ silent: false }) || detectConf == null) {
      return;
    }

    busy = true;
    setButtons();
    setConnStatus("检测中…", "busy");

    let failed = 0;
    for (let i = 0; i < targets.length; i += 1) {
      const image = targets[i];
      setStatus(`YOLO 检测中 (${i + 1}/${targets.length}): ${image.name}`);
      try {
        const result = await yoloDetect(image);
        image.records = result.records;
        image.verdict = result.verdict;
        image.inferenceMs = result.inferenceMs;
      } catch (err) {
        failed += 1;
        image.records = null;
        image.verdict = "pending";
        image.inferenceMs = null;
        setStatus(
          `检测失败 (${i + 1}/${targets.length}): ${image.name} · ${
            err && err.message ? err.message : err
          }`
        );
      }
      if (image.id === activeId) drawPreview(image);
      renderGallery();
      renderResults();
      renderSummary();
    }

    busy = false;
    setButtons();
    setConnStatus(
      engineReady ? weightsStatusText() : "选择权重文件",
      engineReady ? "ready" : "pick"
    );
    if (failed > 0) {
      setStatus(`部分检测失败: ${failed}/${targets.length}`);
    } else {
      setStatus("就绪");
    }
  }

  function csvEscape(value) {
    const s = String(value);
    if (/[",\n\r]/.test(s)) return `"${s.replaceAll('"', '""')}"`;
    return s;
  }

  function formatCoord(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "-1";
    if (Number.isInteger(n)) return String(n);
    return String(Math.round(n * 10) / 10);
  }

  function formatTimeMs(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return "0";
    return String(Math.round(n * 10) / 10);
  }

  function formatConfidence(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "0.00";
    const clamped = Math.min(1, Math.max(0, n));
    return clamped.toFixed(2);
  }

  /**
   * 按 docs/接口规范.md 与附件1（赛题二电池包）生成一行一目标的 CSV 行。
   * 有裂纹 → 仅 Surface_Crack 行；无裂纹 → 恰好一行 Ok 占位。
   */
  function buildRowsForImage(image) {
    const imageId = image.name;
    const tMs = formatTimeMs(
      image.inferenceMs ??
        image.records?.find((r) => r.inference_time_ms != null)?.inference_time_ms ??
        0
    );

    const cracks = (image.records || []).filter(
      (r) => r && r.class_name === CLASS_CRACK
    );

    if (!cracks.length) {
      return [
        [imageId, CLASS_OK, "-1", "-1", "-1", "-1", "-1", tMs].map(csvEscape).join(","),
      ];
    }

    return cracks.map((rec) => {
      let xMin = Number(rec.x_min);
      let yMin = Number(rec.y_min);
      let xMax = Number(rec.x_max);
      let yMax = Number(rec.y_max);
      if (!Number.isFinite(xMin)) xMin = 0;
      if (!Number.isFinite(yMin)) yMin = 0;
      if (!Number.isFinite(xMax)) xMax = xMin + 1;
      if (!Number.isFinite(yMax)) yMax = yMin + 1;
      if (xMax <= xMin) xMax = xMin + 1;
      if (yMax <= yMin) yMax = yMin + 1;

      return [
        imageId,
        CLASS_CRACK,
        formatConfidence(rec.confidence),
        formatCoord(xMin),
        formatCoord(yMin),
        formatCoord(xMax),
        formatCoord(yMax),
        tMs,
      ]
        .map(csvEscape)
        .join(",");
    });
  }

  /** @returns {{ csv: string, imageCount: number, rowCount: number } | null} */
  function buildBatteryPackCsv(sourceImages) {
    const detected = sourceImages.filter(
      (img) => img.verdict !== "pending" && img.records
    );
    if (!detected.length) return null;

    const body = [];
    for (const img of detected) {
      body.push(...buildRowsForImage(img));
    }
    return {
      csv: [CSV_HEADER, ...body].join("\n") + "\n",
      imageCount: detected.length,
      rowCount: body.length,
    };
  }

  function downloadCsvBlob(csvText, filename) {
    const blob = new Blob([csvText], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function todayParts() {
    const d = new Date();
    return {
      year: d.getFullYear(),
      month: d.getMonth() + 1,
      day: d.getDate(),
    };
  }

  function todayYmd() {
    const { year, month, day } = todayParts();
    return `${year}${String(month).padStart(2, "0")}${String(day).padStart(2, "0")}`;
  }

  function daysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
  }

  function sanitizeNamePart(value, fallback) {
    const cleaned = String(value || "")
      .trim()
      .replace(/[\\/:*?"<>|\s]+/g, "")
      .replace(/_+/g, "_")
      .replace(/^_+|_+$/g, "");
    return cleaned || fallback;
  }

  function exportDetailOn() {
    return Boolean(els.exportDetail?.checked);
  }

  function buildExportFilename(line, shift, dateYmd, withDetail) {
    if (!withDetail) return `${EXPORT_PREFIX}.csv`;
    const linePart = sanitizeNamePart(line, "产线");
    const shiftPart = sanitizeNamePart(shift, "班次");
    const datePart = /^\d{8}$/.test(String(dateYmd || "")) ? String(dateYmd) : todayYmd();
    return `${EXPORT_PREFIX}_${linePart}_${shiftPart}_${datePart}.csv`;
  }

  function fillWheelCol(col, values, labels) {
    if (!col) return;
    col.innerHTML = "";
    const top = document.createElement("div");
    top.className = "date-wheel-spacer";
    col.appendChild(top);
    values.forEach((value, idx) => {
      const item = document.createElement("div");
      item.className = "date-wheel-item";
      item.dataset.value = String(value);
      item.textContent = labels[idx];
      col.appendChild(item);
    });
    const bottom = document.createElement("div");
    bottom.className = "date-wheel-spacer";
    col.appendChild(bottom);
  }

  function selectedWheelValue(col) {
    if (!col) return null;
    const idx = Math.round(col.scrollTop / WHEEL_ITEM_H);
    const items = col.querySelectorAll(".date-wheel-item");
    const item = items[Math.max(0, Math.min(items.length - 1, idx))];
    return item ? Number(item.dataset.value) : null;
  }

  function markWheelActive(col) {
    if (!col) return;
    const value = selectedWheelValue(col);
    col.querySelectorAll(".date-wheel-item").forEach((item) => {
      item.classList.toggle("is-active", Number(item.dataset.value) === value);
    });
  }

  function scrollWheelToValue(col, value, smooth) {
    if (!col) return;
    const items = [...col.querySelectorAll(".date-wheel-item")];
    const idx = items.findIndex((item) => Number(item.dataset.value) === Number(value));
    if (idx < 0) return;
    col.scrollTo({
      top: idx * WHEEL_ITEM_H,
      behavior: smooth ? "smooth" : "auto",
    });
    markWheelActive(col);
  }

  function readWheelDate() {
    let year = selectedWheelValue(els.wheelYear) || todayParts().year;
    let month = selectedWheelValue(els.wheelMonth) || todayParts().month;
    let day = selectedWheelValue(els.wheelDay) || todayParts().day;
    const maxDay = daysInMonth(year, month);
    if (day > maxDay) day = maxDay;
    return {
      year,
      month,
      day,
      ymd: `${year}${String(month).padStart(2, "0")}${String(day).padStart(2, "0")}`,
    };
  }

  function rebuildDayWheel(keepDay) {
    const year = selectedWheelValue(els.wheelYear) || todayParts().year;
    const month = selectedWheelValue(els.wheelMonth) || todayParts().month;
    const maxDay = daysInMonth(year, month);
    const days = Array.from({ length: maxDay }, (_, i) => i + 1);
    fillWheelCol(
      els.wheelDay,
      days,
      days.map((d) => `${String(d).padStart(2, "0")}日`)
    );
    const nextDay = Math.min(keepDay || todayParts().day, maxDay);
    scrollWheelToValue(els.wheelDay, nextDay, false);
  }

  function initDateWheels(target) {
    const now = target || todayParts();
    const years = [];
    for (let y = now.year - 3; y <= now.year + 1; y += 1) years.push(y);
    const months = Array.from({ length: 12 }, (_, i) => i + 1);
    fillWheelCol(
      els.wheelYear,
      years,
      years.map((y) => `${y}年`)
    );
    fillWheelCol(
      els.wheelMonth,
      months,
      months.map((m) => `${String(m).padStart(2, "0")}月`)
    );
    rebuildDayWheel(now.day);
    scrollWheelToValue(els.wheelYear, now.year, false);
    scrollWheelToValue(els.wheelMonth, now.month, false);
    scrollWheelToValue(els.wheelDay, now.day, false);
    const date = readWheelDate();
    if (els.exportDate) els.exportDate.value = date.ymd;
  }

  function onWheelScroll(col) {
    if (wheelSyncing) return;
    window.clearTimeout(col._snapTimer);
    col._snapTimer = window.setTimeout(() => {
      wheelSyncing = true;
      const value = selectedWheelValue(col);
      scrollWheelToValue(col, value, true);
      if (col === els.wheelYear || col === els.wheelMonth) {
        const keepDay = selectedWheelValue(els.wheelDay);
        rebuildDayWheel(keepDay);
      }
      const date = readWheelDate();
      if (els.exportDate) els.exportDate.value = date.ymd;
      refreshExportPreview();
      markWheelActive(els.wheelYear);
      markWheelActive(els.wheelMonth);
      markWheelActive(els.wheelDay);
      wheelSyncing = false;
    }, 80);
  }

  function refreshExportPreview() {
    if (!els.exportPreview) return;
    const dateYmd = els.exportDate?.value || readWheelDate().ymd;
    els.exportPreview.textContent = buildExportFilename(
      els.exportLine?.value,
      els.exportShift?.value,
      dateYmd,
      exportDetailOn()
    );
  }

  function closeExportModal() {
    if (!els.exportModal) return;
    els.exportModal.hidden = true;
    pendingExport = null;
  }

  function openExportModal(built) {
    pendingExport = built;
    try {
      const savedLine = localStorage.getItem(LS_LINE);
      const savedShift = localStorage.getItem(LS_SHIFT);
      if (els.exportLine && savedLine) els.exportLine.value = savedLine;
      if (els.exportShift && savedShift) els.exportShift.value = savedShift;
    } catch {
      /* ignore */
    }
    if (els.exportLine && !els.exportLine.value) els.exportLine.value = "A线";
    let detailOn = false;
    try {
      detailOn = localStorage.getItem(LS_DETAIL) === "1";
    } catch {
      /* ignore */
    }
    if (els.exportDetail) els.exportDetail.checked = detailOn;
    if (els.exportDetailFields) els.exportDetailFields.hidden = !detailOn;
    if (detailOn) initDateWheels(todayParts());
    refreshExportPreview();
    els.exportModal.hidden = false;
    window.setTimeout(() => {
      if (!exportDetailOn()) {
        refreshExportPreview();
        return;
      }
      initDateWheels(todayParts());
      refreshExportPreview();
      els.exportLine?.focus();
    }, 40);
  }

  function systemTheme() {
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "night"
        : "day";
    } catch {
      return "day";
    }
  }

  function readStoredTheme() {
    try {
      const saved = localStorage.getItem(LS_THEME);
      if (saved === "day" || saved === "night") return saved;
    } catch {
      /* ignore */
    }
    return null;
  }

  function resolveInitialTheme() {
    return readStoredTheme() || systemTheme();
  }

  function applyTheme(theme, { persist = false } = {}) {
    const mode = theme === "night" ? "night" : "day";
    const themeClass = `theme-${mode}`;
    document.documentElement.classList.remove("theme-day", "theme-night");
    document.documentElement.classList.add(themeClass);
    document.body.classList.remove("theme-day", "theme-night");
    document.body.classList.add(themeClass);
    if (els.themeDayBtn) {
      els.themeDayBtn.classList.toggle("is-active", mode === "day");
      els.themeDayBtn.setAttribute("aria-pressed", mode === "day" ? "true" : "false");
    }
    if (els.themeNightBtn) {
      els.themeNightBtn.classList.toggle("is-active", mode === "night");
      els.themeNightBtn.setAttribute("aria-pressed", mode === "night" ? "true" : "false");
    }
    if (persist) {
      try {
        localStorage.setItem(LS_THEME, mode);
      } catch {
        /* ignore */
      }
    }
  }

  async function saveExportWithFilename(filename) {
    const built = pendingExport;
    if (!built) return;

    const api = window.pywebview && window.pywebview.api;
    if (api && typeof api.save_csv === "function") {
      try {
        const res = await api.save_csv(built.csv, filename);
        if (res && res.ok) {
          closeExportModal();
          setStatus(
            `已导出选中 ${built.imageCount} 张 / ${built.rowCount} 行 → ${res.path}`
          );
          return;
        }
        if (res && res.cancelled) {
          setStatus("已取消导出");
          return;
        }
      } catch {
        /* 回退浏览器下载 */
      }
    }

    downloadCsvBlob(built.csv, filename);
    closeExportModal();
    setStatus(
      `已导出选中 ${built.imageCount} 张 / ${built.rowCount} 行 → ${filename}`
    );
  }

  async function exportCsv() {
    pruneSelection();
    const chosen = selectedImages();
    if (!chosen.length) {
      setStatus("请先勾选要导出的图像，或点击「全选」");
      return;
    }

    const built = buildBatteryPackCsv(chosen);
    if (!built) {
      setStatus("选中的图像尚无检测结果，请先完成检测后再导出");
      return;
    }

    openExportModal(built);
  }

  function drawCrackPath(targetCtx, rec) {
    const poly = Array.isArray(rec.polygon) ? rec.polygon : null;
    if (poly && poly.length >= 3) {
      targetCtx.beginPath();
      targetCtx.moveTo(Number(poly[0][0]), Number(poly[0][1]));
      for (let i = 1; i < poly.length; i += 1) {
        targetCtx.lineTo(Number(poly[i][0]), Number(poly[i][1]));
      }
      targetCtx.closePath();
      return true;
    }
    const x = Number(rec.x_min);
    const y = Number(rec.y_min);
    const w = Number(rec.x_max) - x;
    const h = Number(rec.y_max) - y;
    if (![x, y, w, h].every(Number.isFinite) || w <= 0 || h <= 0) return false;
    targetCtx.beginPath();
    targetCtx.rect(x, y, w, h);
    return true;
  }

  function drawDetections(targetCtx, width, records) {
    if (!targetCtx || !records) return;
    const crackLineW = Math.max(1.5, Math.round(width / 500));
    const boxLineW = Math.max(2, Math.round(width / 400));
    for (const rec of records) {
      if (rec.class_name === "Ok") continue;

      // 1) 裂纹分割轮廓：蓝色填充 + 蓝边
      if (drawCrackPath(targetCtx, rec)) {
        targetCtx.fillStyle = "rgba(0, 120, 255, 0.42)";
        targetCtx.fill();
        targetCtx.strokeStyle = "#00a8ff";
        targetCtx.lineWidth = crackLineW;
        targetCtx.lineJoin = "round";
        targetCtx.lineCap = "round";
        targetCtx.stroke();
      }

      // 2) 外接红色矩形框 + 置信度（与 CSV 的 xyxy 一致）
      const x = Number(rec.x_min);
      const y = Number(rec.y_min);
      const w = Number(rec.x_max) - x;
      const h = Number(rec.y_max) - y;
      if (![x, y, w, h].every(Number.isFinite) || w <= 0 || h <= 0) continue;

      targetCtx.lineWidth = boxLineW;
      targetCtx.strokeStyle = "#ff4d4f";
      targetCtx.strokeRect(x, y, w, h);

      const label = `Surface_Crack ${Number(rec.confidence).toFixed(2)}`;
      targetCtx.font = `${Math.max(12, Math.round(width / 55))}px IBM Plex Mono, monospace`;
      const pad = 4;
      const tw = targetCtx.measureText(label).width;
      const th = Math.max(16, Math.round(width / 50));
      targetCtx.fillStyle = "#ff4d4f";
      targetCtx.fillRect(x, Math.max(0, y - th - 2), tw + pad * 2, th + 2);
      targetCtx.fillStyle = "#fff";
      targetCtx.fillText(label, x + pad, Math.max(th - 4, y - 6));
    }
  }

  function drawPreview(image) {
    if (!image) {
      els.canvas.style.display = "none";
      els.placeholder.style.display = "grid";
      els.currentName.textContent = "—";
      els.currentName.removeAttribute("title");
      els.currentVerdict.textContent = "—";
      els.currentVerdict.className = "tag";
      els.currentTime.textContent = "—";
      if (els.expandBtn) els.expandBtn.disabled = true;
      return;
    }

    if (els.expandBtn) els.expandBtn.disabled = false;

    const img = new Image();
    img.onload = () => {
      els.canvas.width = img.naturalWidth;
      els.canvas.height = img.naturalHeight;
      ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
      ctx.drawImage(img, 0, 0);
      drawDetections(ctx, img.naturalWidth, image.records);
      els.canvas.style.display = "block";
      els.placeholder.style.display = "none";
    };
    img.src = image.url;

    const nameLabel = `${image.name}  ·  ${image.width}×${image.height}`;
    els.currentName.textContent = nameLabel;
    els.currentName.title = nameLabel;
    if (image.verdict === "pending") {
      els.currentVerdict.textContent = "待检";
      els.currentVerdict.className = "tag pending";
      els.currentTime.textContent = "—";
    } else if (image.verdict === "ok") {
      els.currentVerdict.textContent = "OK";
      els.currentVerdict.className = "tag ok";
      els.currentTime.textContent = `${image.inferenceMs} ms`;
    } else {
      els.currentVerdict.textContent = "NG";
      els.currentVerdict.className = "tag ng";
      els.currentTime.textContent = `${image.inferenceMs} ms`;
    }
  }

  function closeCompareModal() {
    if (!els.compareModal) return;
    els.compareModal.hidden = true;
  }

  function openCompareModal() {
    const image = activeImage();
    if (!image || !els.compareModal) return;

    els.compareSub.textContent = `${image.name}  ·  ${image.width}×${image.height}`;
    els.compareBefore.src = image.url;
    els.compareModal.hidden = false;

    const hasResult = Boolean(image.records && image.verdict !== "pending");
    if (els.compareAfterEmpty) {
      els.compareAfterEmpty.classList.toggle("show", !hasResult);
    }
    if (!compareCtx || !els.compareAfter) return;

    const img = new Image();
    img.onload = () => {
      els.compareAfter.width = img.naturalWidth;
      els.compareAfter.height = img.naturalHeight;
      compareCtx.clearRect(0, 0, els.compareAfter.width, els.compareAfter.height);
      compareCtx.drawImage(img, 0, 0);
      if (hasResult) {
        drawDetections(compareCtx, img.naturalWidth, image.records);
      }
    };
    img.src = image.url;
  }

  function renderGallery() {
    pruneSelection();
    els.imageCount.textContent = String(images.length);
    if (els.selectedInfo) {
      els.selectedInfo.textContent = selectedIds.size
        ? `已选 ${selectedIds.size}`
        : "未选中";
    }
    els.gallery.querySelectorAll(".gallery-item").forEach((n) => n.remove());

    if (!images.length) {
      els.galleryEmpty.style.display = "grid";
      return;
    }
    els.galleryEmpty.style.display = "none";

    for (const image of images) {
      const checked = selectedIds.has(image.id);
      const item = document.createElement("div");
      item.className = `gallery-item${image.id === activeId ? " active" : ""}${
        checked ? " selected" : ""
      }`;
      item.setAttribute("role", "button");
      item.tabIndex = 0;
      item.innerHTML = `
        <label class="gallery-check" title="选中以导出">
          <input type="checkbox" ${checked ? "checked" : ""} aria-label="选中 ${escapeHtml(image.name)}" />
        </label>
        <img src="${image.url}" alt="" />
        <div class="name" title="${escapeHtml(image.name)}">${escapeHtml(image.name)}</div>
        <span class="tag ${image.verdict}">${labelOf(image.verdict)}</span>
        <button type="button" class="gallery-remove" title="删除此图像" aria-label="删除 ${escapeHtml(image.name)}">×</button>
      `;
      item.addEventListener("click", () => {
        activeId = image.id;
        renderAll();
      });
      item.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activeId = image.id;
          renderAll();
        }
      });
      const check = item.querySelector(".gallery-check");
      const checkbox = item.querySelector('input[type="checkbox"]');
      check.addEventListener("click", (e) => e.stopPropagation());
      checkbox.addEventListener("change", (e) => {
        e.stopPropagation();
        toggleSelect(image.id);
      });
      const removeBtn = item.querySelector(".gallery-remove");
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        removeImage(image.id);
      });
      els.gallery.appendChild(item);
    }
  }

  function labelOf(verdict) {
    if (verdict === "ok") return "OK";
    if (verdict === "ng") return "NG";
    return "待检";
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderResults() {
    const current = activeImage();
    const rows = current?.records || [];
    els.resultCount.textContent = String(rows.length);

    if (!rows.length) {
      els.resultBody.innerHTML =
        '<tr class="empty-row"><td colspan="4">暂无结果，请先运行检测</td></tr>';
      return;
    }

    els.resultBody.innerHTML = rows
      .map((rec) => {
        const conf =
          rec.class_name === "Ok" ? "-1" : Number(rec.confidence).toFixed(2);
        const box =
          rec.class_name === "Ok"
            ? "-1,-1,-1,-1"
            : `${rec.x_min},${rec.y_min},${rec.x_max},${rec.y_max}`;
        return `<tr>
          <td>${escapeHtml(rec.image_id)}</td>
          <td>${escapeHtml(rec.class_name)}</td>
          <td>${conf}</td>
          <td>${box}</td>
        </tr>`;
      })
      .join("");
  }

  function renderSummary() {
    const detected = images.filter((img) => img.verdict !== "pending");
    const ng = detected.filter((img) => img.verdict === "ng").length;
    const ok = detected.filter((img) => img.verdict === "ok").length;
    els.statTotal.textContent = String(detected.length);
    els.statNg.textContent = String(ng);
    els.statOk.textContent = String(ok);
    els.sessionInfo.textContent = images.length
      ? `已导入 ${images.length} 张 · 已检 ${detected.length} 张`
      : "未导入图像";
  }

  function setButtons() {
    const hasImages = images.length > 0;
    const hasActive = Boolean(activeImage());
    const hasSelection = selectedIds.size > 0;
    const canExport = selectedImages().some(
      (img) => img.verdict !== "pending" && img.records
    );
    els.clearBtn.disabled = !hasSelection || busy;
    if (els.selectAllBtn) {
      els.selectAllBtn.disabled = !hasImages || busy;
      els.selectAllBtn.textContent = allSelected() ? "取消全选" : "全选";
    }
    els.detectOneBtn.disabled = !hasActive || busy || !engineReady;
    els.detectAllBtn.disabled = !hasSelection || busy || !engineReady;
    els.exportBtn.disabled = !canExport || busy;
    els.fileInput.disabled = busy;
    els.folderInput.disabled = busy;
    if (els.connStatus) els.connStatus.disabled = choosingWeights || busy;
    if (els.confCurrent) els.confCurrent.disabled = busy || choosingWeights;
  }

  function renderAll() {
    renderGallery();
    drawPreview(activeImage());
    renderResults();
    renderSummary();
    setButtons();
  }

  els.fileInput.addEventListener("change", async (e) => {
    await importFiles(e.target.files);
    e.target.value = "";
  });

  els.folderInput.addEventListener("change", async (e) => {
    await importFiles(e.target.files);
    e.target.value = "";
  });

  els.clearBtn.addEventListener("click", clearSelected);
  if (els.selectAllBtn) {
    els.selectAllBtn.addEventListener("click", selectAllImages);
  }
  els.detectOneBtn.addEventListener("click", () => {
    const img = activeImage();
    if (img) runDetect([img]);
  });
  els.detectAllBtn.addEventListener("click", () => {
    pruneSelection();
    const chosen = selectedImages();
    if (!chosen.length) {
      setStatus("请先勾选要检测的图像，或点击「全选」");
      return;
    }
    runDetect(chosen);
  });
  els.exportBtn.addEventListener("click", exportCsv);

  if (els.exportDetail) {
    els.exportDetail.addEventListener("change", () => {
      const on = exportDetailOn();
      if (els.exportDetailFields) els.exportDetailFields.hidden = !on;
      try {
        localStorage.setItem(LS_DETAIL, on ? "1" : "0");
      } catch {
        /* ignore */
      }
      if (on) {
        initDateWheels(todayParts());
        window.setTimeout(() => {
          initDateWheels(todayParts());
          refreshExportPreview();
          els.exportLine?.focus();
        }, 40);
        return;
      }
      refreshExportPreview();
    });
  }
  if (els.exportLine) {
    els.exportLine.addEventListener("input", refreshExportPreview);
  }
  if (els.exportShift) {
    els.exportShift.addEventListener("change", refreshExportPreview);
  }
  [els.wheelYear, els.wheelMonth, els.wheelDay].forEach((col) => {
    if (!col) return;
    col.addEventListener("scroll", () => onWheelScroll(col), { passive: true });
  });
  if (els.exportForm) {
    els.exportForm.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!pendingExport) return;
      const withDetail = exportDetailOn();
      const line = els.exportLine?.value || "";
      const shift = els.exportShift?.value || "";
      if (withDetail && !sanitizeNamePart(line, "")) {
        setStatus("请填写产线");
        els.exportLine?.focus();
        return;
      }
      const date = readWheelDate();
      if (els.exportDate) els.exportDate.value = date.ymd;
      const filename = buildExportFilename(line, shift, date.ymd, withDetail);
      if (withDetail) {
        try {
          localStorage.setItem(LS_LINE, sanitizeNamePart(line, "A线"));
          localStorage.setItem(LS_SHIFT, sanitizeNamePart(shift, "早班"));
        } catch {
          /* ignore */
        }
      }
      saveExportWithFilename(filename);
    });
  }
  if (els.themeDayBtn) {
    els.themeDayBtn.addEventListener("click", () =>
      applyTheme("day", { persist: true })
    );
  }
  if (els.themeNightBtn) {
    els.themeNightBtn.addEventListener("click", () =>
      applyTheme("night", { persist: true })
    );
  }
  if (els.connStatus) {
    els.connStatus.addEventListener("click", () => {
      chooseWeightsFile();
    });
  }
  if (els.confCurrent) {
    els.confCurrent.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        applyConfInput();
        els.confCurrent.blur();
      }
    });
    els.confCurrent.addEventListener("blur", () => {
      if (String(els.confCurrent.value || "").trim()) {
        applyConfInput({ silent: true });
      } else {
        detectConf = null;
      }
    });
  }
  if (els.alertOk) els.alertOk.addEventListener("click", closeAlert);
  if (els.alertClose) els.alertClose.addEventListener("click", closeAlert);
  if (els.alertBackdrop) els.alertBackdrop.addEventListener("click", closeAlert);
  try {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystemTheme = () => {
      if (!readStoredTheme()) applyTheme(systemTheme());
    };
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onSystemTheme);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(onSystemTheme);
    }
  } catch {
    /* ignore */
  }
  if (els.exportCancel) {
    els.exportCancel.addEventListener("click", () => {
      closeExportModal();
      setStatus("已取消导出");
    });
  }
  if (els.exportClose) {
    els.exportClose.addEventListener("click", () => {
      closeExportModal();
      setStatus("已取消导出");
    });
  }
  if (els.exportBackdrop) {
    els.exportBackdrop.addEventListener("click", () => {
      closeExportModal();
      setStatus("已取消导出");
    });
  }

  if (els.expandBtn) {
    els.expandBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openCompareModal();
    });
  }
  if (els.compareClose) {
    els.compareClose.addEventListener("click", closeCompareModal);
  }
  if (els.compareBackdrop) {
    els.compareBackdrop.addEventListener("click", closeCompareModal);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (els.alertModal && !els.alertModal.hidden) {
      closeAlert();
      return;
    }
    if (els.exportModal && !els.exportModal.hidden) {
      closeExportModal();
      setStatus("已取消导出");
      return;
    }
    if (els.compareModal && !els.compareModal.hidden) {
      closeCompareModal();
    }
  });

  renderAll();
  applyTheme(resolveInitialTheme());
  clearConfField();
  setConnStatus("选择权重文件", "pick");
  setStatus("请先点击右上角选择 .pt 权重文件");

  // 桌面端 loaded 后会回调 onEngineReady；浏览器直开则提示需走 desktop.py
  window.setTimeout(async () => {
    const api = pyApi();
    if (!api) {
      setConnStatus("浏览器预览", "error");
      setStatus("浏览器预览无 YOLO；请运行: python app/desktop.py");
      return;
    }
    if (typeof api.get_engine_status === "function") {
      try {
        const st = await api.get_engine_status();
        if (st && st.model_loaded) {
          onEngineReady({
            ok: true,
            conf: st.conf,
            imgsz: st.imgsz,
            name: st.weights_name,
            weights: st.weights,
          });
        } else {
          onEngineReady({ ok: false, need_weights: true });
        }
      } catch {
        onEngineReady({ ok: false, need_weights: true });
      }
    }
  }, 300);
})();
