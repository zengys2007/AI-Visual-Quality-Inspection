(() => {
  "use strict";

  const IMAGE_EXT = /\.(jpe?g|png|bmp|webp)$/i;
  const TEAM_NAME = "视觉检测团队";
  /** 赛题二电池包：仅允许这两类；忽略窗帘布 Hole / Ink / Broken_Filament */
  const CLASS_CRACK = "Surface_Crack";
  const CLASS_OK = "Ok";
  const CSV_HEADER =
    "image_id,class_name,confidence,x_min,y_min,x_max,y_max,inference_time_ms";

  /** @type {{ id: string, name: string, url: string, width: number, height: number, records: object[] | null, verdict: 'pending'|'ok'|'ng', inferenceMs: number | null }[]} */
  let images = [];
  let activeId = null;
  /** @type {Set<string>} 导出用多选集合（与预览 activeId 独立） */
  let selectedIds = new Set();
  let busy = false;

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
    statTotal: document.getElementById("statTotal"),
    statNg: document.getElementById("statNg"),
    statOk: document.getElementById("statOk"),
  };

  const ctx = els.canvas.getContext("2d");

  function setStatus(msg) {
    els.statusMsg.textContent = msg;
  }

  function activeImage() {
    return images.find((img) => img.id === activeId) || null;
  }

  function loadImageMeta(file, url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () =>
        resolve({
          id: `${file.name}_${file.size}_${file.lastModified}`,
          name: file.name,
          url,
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
          entry.dataUrl
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

  function hashName(name) {
    let h = 0;
    for (let i = 0; i < name.length; i += 1) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return h;
  }

  function mockDetect(image) {
    const seed = hashName(image.name);
    const inferenceMs = Math.round((22 + (seed % 40) + Math.random() * 8) * 10) / 10;
    const isOk = seed % 5 === 0;

    if (isOk) {
      return {
        verdict: "ok",
        inferenceMs,
        records: [
          {
            image_id: image.name,
            class_name: CLASS_OK,
            confidence: -1,
            x_min: -1,
            y_min: -1,
            x_max: -1,
            y_max: -1,
            inference_time_ms: inferenceMs,
          },
        ],
      };
    }

    const count = 1 + (seed % 3);
    const records = [];
    for (let i = 0; i < count; i += 1) {
      const w = Math.max(40, Math.floor(image.width * (0.08 + ((seed >> i) % 10) / 100)));
      const h = Math.max(30, Math.floor(image.height * (0.06 + ((seed >> (i + 2)) % 10) / 100)));
      const xMin = Math.floor(((seed + i * 97) % Math.max(1, image.width - w)));
      const yMin = Math.floor(((seed + i * 53) % Math.max(1, image.height - h)));
      const conf = Math.round((0.55 + ((seed >> (i + 1)) % 40) / 100) * 100) / 100;
      records.push({
        image_id: image.name,
        class_name: CLASS_CRACK,
        confidence: conf,
        x_min: xMin,
        y_min: yMin,
        x_max: xMin + w,
        y_max: yMin + h,
        inference_time_ms: inferenceMs,
      });
    }

    return { verdict: "ng", inferenceMs, records };
  }

  async function runDetect(targets) {
    if (busy || !targets.length) return;
    busy = true;
    setButtons();

    for (let i = 0; i < targets.length; i += 1) {
      const image = targets[i];
      setStatus(`Mock 检测中 (${i + 1}/${targets.length}): ${image.name}`);
      await new Promise((r) => setTimeout(r, 180 + Math.random() * 220));
      const result = mockDetect(image);
      image.records = result.records;
      image.verdict = result.verdict;
      image.inferenceMs = result.inferenceMs;
      if (image.id === activeId) drawPreview(image);
      renderGallery();
      renderResults();
      renderSummary();
    }

    busy = false;
    setButtons();
    setStatus(
      targets.length === 1
        ? `单张检测完成: ${targets[0].name}`
        : `批量检测完成: ${targets.length} 张`
    );
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

    const filename = `${TEAM_NAME}_检测结果.csv`;
    const api = window.pywebview && window.pywebview.api;

    if (api && typeof api.save_csv === "function") {
      try {
        const res = await api.save_csv(built.csv, filename);
        if (res && res.ok) {
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
    setStatus(
      `已导出选中 ${built.imageCount} 张 / ${built.rowCount} 行 → ${filename}`
    );
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
      return;
    }

    const img = new Image();
    img.onload = () => {
      els.canvas.width = img.naturalWidth;
      els.canvas.height = img.naturalHeight;
      ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
      ctx.drawImage(img, 0, 0);

      if (image.records) {
        for (const rec of image.records) {
          if (rec.class_name === "Ok") continue;
          const x = rec.x_min;
          const y = rec.y_min;
          const w = rec.x_max - rec.x_min;
          const h = rec.y_max - rec.y_min;
          ctx.lineWidth = Math.max(2, Math.round(img.naturalWidth / 400));
          ctx.strokeStyle = "#ff4d4f";
          ctx.fillStyle = "rgba(255, 77, 79, 0.14)";
          ctx.fillRect(x, y, w, h);
          ctx.strokeRect(x, y, w, h);

          const label = `Surface_Crack ${Number(rec.confidence).toFixed(2)}`;
          ctx.font = `${Math.max(12, Math.round(img.naturalWidth / 55))}px IBM Plex Mono, monospace`;
          const pad = 4;
          const tw = ctx.measureText(label).width;
          const th = Math.max(16, Math.round(img.naturalWidth / 50));
          ctx.fillStyle = "#ff4d4f";
          ctx.fillRect(x, Math.max(0, y - th - 2), tw + pad * 2, th + 2);
          ctx.fillStyle = "#fff";
          ctx.fillText(label, x + pad, Math.max(th - 4, y - 6));
        }
      }

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
    els.detectOneBtn.disabled = !hasActive || busy;
    els.detectAllBtn.disabled = !hasImages || busy;
    els.exportBtn.disabled = !canExport || busy;
    els.fileInput.disabled = busy;
    els.folderInput.disabled = busy;
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
  els.detectAllBtn.addEventListener("click", () => runDetect([...images]));
  els.exportBtn.addEventListener("click", exportCsv);

  renderAll();
  setStatus("就绪 · Mock 模式");
})();
