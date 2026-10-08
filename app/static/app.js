(() => {
  "use strict";

  const IMAGE_EXT = /\.(jpe?g|png|bmp|webp)$/i;
  const TEAM_NAME = "视觉检测团队";

  /** @type {{ id: string, name: string, url: string, width: number, height: number, records: object[] | null, verdict: 'pending'|'ok'|'ng', inferenceMs: number | null }[]} */
  let images = [];
  let activeId = null;
  let busy = false;

  const els = {
    fileInput: document.getElementById("fileInput"),
    folderInput: document.getElementById("folderInput"),
    clearBtn: document.getElementById("clearBtn"),
    detectOneBtn: document.getElementById("detectOneBtn"),
    detectAllBtn: document.getElementById("detectAllBtn"),
    exportBtn: document.getElementById("exportBtn"),
    gallery: document.getElementById("gallery"),
    galleryEmpty: document.getElementById("galleryEmpty"),
    imageCount: document.getElementById("imageCount"),
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

    if (!added.length) {
      setStatus("没有新增图像（可能与已导入文件重名）");
      return;
    }

    if (!activeId) activeId = added[0].id;
    renderAll();
    setStatus(`已导入 ${added.length} 张图像`);
  }

  function clearAll() {
    images.forEach((img) => URL.revokeObjectURL(img.url));
    images = [];
    activeId = null;
    renderAll();
    setStatus("已清空");
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
            class_name: "Ok",
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
        class_name: "Surface_Crack",
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

  function exportCsv() {
    const detected = images.filter((img) => img.records && img.records.length);
    if (!detected.length) {
      setStatus("没有可导出的检测结果");
      return;
    }

    const header =
      "image_id,class_name,confidence,x_min,y_min,x_max,y_max,inference_time_ms";
    const rows = [];
    for (const img of detected) {
      for (const rec of img.records) {
        const conf =
          rec.class_name === "Ok" ? "-1" : Number(rec.confidence).toFixed(2);
        rows.push(
          [
            rec.image_id,
            rec.class_name,
            conf,
            rec.x_min,
            rec.y_min,
            rec.x_max,
            rec.y_max,
            rec.inference_time_ms,
          ].join(",")
        );
      }
    }

    const blob = new Blob([[header, ...rows].join("\n") + "\n"], {
      type: "text/csv;charset=utf-8",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${TEAM_NAME}_检测结果.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    setStatus(`已导出 ${detected.length} 张图像的 CSV`);
  }

  function drawPreview(image) {
    if (!image) {
      els.canvas.style.display = "none";
      els.placeholder.style.display = "grid";
      els.currentName.textContent = "—";
      els.currentVerdict.textContent = "—";
      els.currentVerdict.className = "verdict";
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
          ctx.strokeStyle = "#c2410c";
          ctx.fillStyle = "rgba(194, 65, 12, 0.14)";
          ctx.fillRect(x, y, w, h);
          ctx.strokeRect(x, y, w, h);

          const label = `Surface_Crack ${Number(rec.confidence).toFixed(2)}`;
          ctx.font = `${Math.max(12, Math.round(img.naturalWidth / 55))}px IBM Plex Mono, monospace`;
          const pad = 4;
          const tw = ctx.measureText(label).width;
          const th = Math.max(16, Math.round(img.naturalWidth / 50));
          ctx.fillStyle = "#c2410c";
          ctx.fillRect(x, Math.max(0, y - th - 2), tw + pad * 2, th + 2);
          ctx.fillStyle = "#fff";
          ctx.fillText(label, x + pad, Math.max(th - 4, y - 6));
        }
      }

      els.canvas.style.display = "block";
      els.placeholder.style.display = "none";
    };
    img.src = image.url;

    els.currentName.textContent = `${image.name} (${image.width}×${image.height})`;
    if (image.verdict === "pending") {
      els.currentVerdict.textContent = "未检测";
      els.currentVerdict.className = "verdict";
      els.currentTime.textContent = "—";
    } else if (image.verdict === "ok") {
      els.currentVerdict.textContent = "OK";
      els.currentVerdict.className = "verdict ok";
      els.currentTime.textContent = `${image.inferenceMs} ms`;
    } else {
      els.currentVerdict.textContent = "NG";
      els.currentVerdict.className = "verdict ng";
      els.currentTime.textContent = `${image.inferenceMs} ms`;
    }
  }

  function renderGallery() {
    els.imageCount.textContent = String(images.length);
    els.gallery.querySelectorAll(".gallery-item").forEach((n) => n.remove());

    if (!images.length) {
      els.galleryEmpty.style.display = "grid";
      return;
    }
    els.galleryEmpty.style.display = "none";

    for (const image of images) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `gallery-item${image.id === activeId ? " active" : ""}`;
      item.innerHTML = `
        <img src="${image.url}" alt="" />
        <div class="name">${escapeHtml(image.name)}</div>
        <span class="tag ${image.verdict}">${labelOf(image.verdict)}</span>
      `;
      item.addEventListener("click", () => {
        activeId = image.id;
        renderAll();
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
    const hasResults = images.some((img) => img.records);
    els.clearBtn.disabled = !hasImages || busy;
    els.detectOneBtn.disabled = !hasActive || busy;
    els.detectAllBtn.disabled = !hasImages || busy;
    els.exportBtn.disabled = !hasResults || busy;
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

  els.clearBtn.addEventListener("click", clearAll);
  els.detectOneBtn.addEventListener("click", () => {
    const img = activeImage();
    if (img) runDetect([img]);
  });
  els.detectAllBtn.addEventListener("click", () => runDetect([...images]));
  els.exportBtn.addEventListener("click", exportCsv);

  renderAll();
  setStatus("就绪 · Mock 模式");
})();
