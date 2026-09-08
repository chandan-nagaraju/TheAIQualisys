(function () {
  if (window.self !== window.top) {
    document.documentElement.classList.add("fir-embedded");
  }
  var boot = {};
  try {
    var bootEl = document.getElementById("fir-preview-boot");
    boot = JSON.parse((bootEl && bootEl.textContent) || "{}") || {};
  } catch (err) {
    boot = {};
  }
  var globalSettings = boot.settings || {};
  var FIR_SPEC_DATA = boot.spec_data || [];
  var FIR_CCP_DATA = boot.ccp_data || [];
  var FIR_MATERIAL_DATA = boot.material_data || [];
  var FIR_COATING_DATA = boot.coating_data || [];
  var firQuery = boot.query || {};
  var urlParams = new URLSearchParams(window.location.search);
  function firQueryParam(name) {
    var fromUrl = urlParams.get(name);
    if (fromUrl != null && String(fromUrl).length) return fromUrl;
    var b = firQuery[name];
    return b == null ? "" : String(b);
  }
  /** html2pdf raster tuning — same for single download and inspection-page batch ZIP (full quality). */
  var FIR_PDF_JPEG_QUALITY = 0.72;
  var FIR_PDF_CANVAS_SCALE = 1.12;
  var FIR_PDF_IMG_JPEG = 0.72;
  /** No downscale for logo/signature grayscale prep (full pixel count for sharp PDFs). */
  var FIR_PDF_IMG_MAX_EDGE = 100000;

  const partName = firQueryParam('partName');
  const description = firQueryParam('description');
  const drawRev = firQueryParam('drawRev');
  const vendorCode = firQueryParam('vendorCode');
  const customer = firQueryParam('customer');
  const reportNo = firQueryParam('reportNo');
  const invoiceNo = firQueryParam('invoiceNo');
  function firNormalizeReportDate(raw) {
    var s = String(raw || "").trim();
    if (!s) return "";
    if (/^\d{1,2}\s*[-/]\s*\d{1,2}$/.test(s)) return "";
    var dmY = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
    if (dmY) {
      var y = parseInt(dmY[3], 10);
      if (y >= 2000 && y <= 2100) {
        return dmY[1].padStart(2, "0") + "." + dmY[2].padStart(2, "0") + "." + dmY[3];
      }
      return "";
    }
    var iso = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) {
      var yi = parseInt(iso[1], 10);
      if (yi >= 2000 && yi <= 2100) {
        return iso[3] + "." + iso[2] + "." + iso[1];
      }
      return "";
    }
    if (/^\d{1,5}$/.test(s)) return "";
    return "";
  }
  const reportDate = firNormalizeReportDate(firQueryParam('reportDate'));
  const lotQty = firQueryParam('quantity');
  const sampleSize = firQueryParam('sampleSize');
  const noOfParamsParam = parseInt(firQueryParam('noOfParams'), 10);
  const totalRows = FIR_SPEC_DATA.length > 0 ? FIR_SPEC_DATA.length : (noOfParamsParam || 18);

  /**
   * How many "Actual Measured Values" columns to use (1–5) for sections A, B, D.
   * Table always shows 5 columns; only the first N get data. Invalid/empty → 5 (legacy URLs).
   * Values above 5 are treated as 5 (sample size is never expected > 5 in production).
   */
  function firParseSampleSizeN(raw) {
    const s = (raw == null || raw === undefined) ? "" : String(raw).trim();
    if (!s) return 5;
    const n = parseInt(s, 10);
    if (isNaN(n)) return 5;
    if (n < 1) return 1;
    if (n > 5) return 5;
    return n;
  }

  function firGetMeasuredColumnCount() {
    const el = document.getElementById("firSampleSizeInput");
    return firParseSampleSizeN(el ? el.value : sampleSize);
  }

  function firApplyMeasuredColumnAvailability() {
    const n = firGetMeasuredColumnCount();
    ["dimension-table", "ccp-table", "coating-table"].forEach(function(tableId) {
      const table = document.getElementById(tableId);
      if (!table) return;
      const headNums = table.querySelectorAll("thead .fir-col-head-num");
      headNums.forEach(function(th, idx) {
        const col = idx + 1;
        th.classList.toggle("fir-measured-inactive", col > n);
      });
      table.querySelectorAll("tbody tr").forEach(function(tr) {
        if (firIsNoCpiRow(tr)) return;
        firSyncMilliporeRowLayout(tr);
        if (firIsMilliporeRow(tr)) {
          var mpTd = tr.querySelector("td.fir-millipore-merged");
          if (mpTd) mpTd.classList.remove("fir-measured-inactive");
          var mpInp = tr.querySelector("input.actual-value");
          if (mpInp) mpInp.disabled = false;
          return;
        }
        const cells = tr.querySelectorAll(":scope > td");
        for (var ci = 5; ci <= 9; ci++) {
          const td = cells[ci];
          if (!td) continue;
          const col = ci - 4;
          const inactive = col > n;
          td.classList.toggle("fir-measured-inactive", inactive);
          const inp = td.querySelector("input.actual-value") || td.querySelector('input[type="text"]');
          if (inp) {
            if (inactive) {
              inp.value = "";
              inp.disabled = true;
            } else {
              inp.disabled = false;
            }
          }
        }
      });
    });
  }

  /** Visual inspection: qualitative pass recorded as OK in measured cells. */
  function firIsVisualMethod(raw) {
    var m = String(raw || "").trim().toUpperCase();
    return m === "VIS" || m === "VISUAL" || m === "VISUAL INSPECTION";
  }

  function firIsVisualParameter(paramRaw) {
    var p = String(paramRaw || "").trim().toUpperCase();
    if (!p) return false;
    return /\bVISUAL\b|\bRUST\b|\bDENT\b|\bDAMAGE\b|\bSCORING\b|\bWELD\b|\bBURR\b|\bAPPEARANCE\b/.test(p);
  }

  function firIsVisualSpecification(specRaw) {
    var s = String(specRaw || "").trim().toUpperCase();
    if (!s) return false;
    return /\bNOT\s+ALLOWED\b|\bNOT\s+PERMITTED\b|\bNO\s+DEFECT\b|\bFREE\s+FROM\b/.test(s);
  }

  /** QR code verification — parameter contains "QR code"; measured values are OK only. */
  function firIsQrCodeParameter(paramRaw) {
    return /\bQR\s*CODE\b/i.test(String(paramRaw || ""));
  }

  function firIsQrScannerMethod(raw) {
    var u = String(raw || "").trim().replace(/\s+/g, " ").toUpperCase();
    if (!u) return false;
    if (u === "QRS" || u === "QR SCANNER" || u === "QR SCAN") return true;
    return /\bQR\b/.test(u) && /\bSCAN/.test(u);
  }

  /** GD&T shop gauges — flatness / parallelism / perpendicularity; actual = OK or numeric. */
  function firIsFlatnessParameter(paramRaw) {
    return /\b(?:FLATNESS|FLATENESS)\b/i.test(String(paramRaw || ""));
  }

  function firIsParallelismParameter(paramRaw) {
    return /\bPARALLEL(?:ISM)?\b/i.test(String(paramRaw || ""));
  }

  function firIsPerpendicularityParameter(paramRaw) {
    return /\bPERPEND(?:ICULAR(?:ITY)?|IVULAR(?:ITY)?)\b/i.test(String(paramRaw || ""));
  }

  function firIsGdtShopGaugeParameter(paramRaw) {
    return (
      firIsFlatnessParameter(paramRaw) ||
      firIsParallelismParameter(paramRaw) ||
      firIsPerpendicularityParameter(paramRaw)
    );
  }

  function firIsFeelerGaugeMethod(raw) {
    var u = String(raw || "").trim().toUpperCase();
    return u === "FG" || /\bFEELER\b/.test(u);
  }

  function firIsParallelGaugeMethod(raw) {
    return /\bPARALLEL\s*GAU/i.test(String(raw || ""));
  }

  function firIsPerpendicularGaugeMethod(raw) {
    return /\bPERPEND(?:ICULAR|IVULAR)?\s*GAU/i.test(String(raw || ""));
  }

  function firIsHeightGaugeMethod(raw) {
    if (firIsDimensionalMeasuringMethod(raw)) {
      var u = String(raw || "").trim().toUpperCase();
      if (/^DHG$|^DHI$|^VHG$|^HG$|^V\.?H\.?G\.?$/.test(u)) return true;
      if (/HEIGHT\s*GAU|HIEGHT|DIGITAL\s*HEIGHT|VERNIER\s*HEIGHT/.test(u)) return true;
    }
    return false;
  }

  /** GD&T flatness / parallelism / perpendicularity: OK for pass-fail gauges; numeric for height gauge. */
  function firGdtParameterUsesQualitativeMeasured(paramRaw, methodRaw) {
    var param = String(paramRaw || "").trim();
    var method = String(methodRaw || "").trim();
    if (!firIsGdtShopGaugeParameter(param)) return false;
    if (firIsHeightGaugeMethod(method)) return false;
    if (firIsDimensionalMeasuringMethod(method)) return false;
    return true;
  }

  /**
   * Thread plug gauge — TPG or full phrase (case-insensitive).
   * Also accepts common truncation/typo (e.g. "hread plug gau…").
   */
  function firIsThreadPlugGaugeMethod(raw) {
    var u = String(raw || "").trim().replace(/\s+/g, " ").toUpperCase();
    if (u === "TPG") return true;
    if (u === "THREAD PLUG GAUGE") return true;
    var letters = String(raw || "").replace(/[^A-Za-z]/g, "").toUpperCase();
    if (letters.indexOf("THREADPLUGGAUGE") !== -1) return true;
    if (letters.indexOf("HREADPLUGGAUG") !== -1) return true;
    return false;
  }

  /**
   * Instruments that read a numeric size (mm, R, °) — autofill uses specification, not OK.
   * Checked before pass/fail gauge rules so "Vernier height gauge" stays dimensional.
   */
  function firIsDimensionalMeasuringMethod(raw) {
    var u = String(raw || "").trim().toUpperCase();
    if (!u) return false;
    if (/^DVC$|^DHG$|^DHI$|^DMM$|^MM$|^BP$|^B\.P\.?$|^RG$|^R\.G\.?$|^VHG$|^HG$|^V\.?H\.?G\.?$/.test(u)) return true;
    if (/RADIUS\s*(GAU|GAGE)/.test(u)) return true;
    if (/VERNIER|CALIPER|CALLIPER|VENIRE/.test(u)) return true;
    if (/HEIGHT\s*GAU|HIEGHT\s*GAU|HEIGHT\s*GAGE|HIEGHT/.test(u)) return true;
    if (/DIAL\s*GAU|D\.?\s*GAU|DIAL\s*INDICATOR/.test(u)) return true;
    if (/MICROMETER|\bMIC\b|BORE\s*GAU|DEPTH\s*GAU|DEPTH\s*MIC/.test(u)) return true;
    if (/COORDINATE\s*MEASURING|SURFACE\s*PLATE/.test(u)) return true;
    if (/STEEL\s*RULE|\bSCALE\b|\bRULER\b/.test(u)) return true;
    if (/^DFT\b|DFT\s*METER|^DFT$/.test(u)) return true;
    return false;
  }

  /**
   * Go / no-go shop gauges — measured columns are OK only (parallel, slip, weld fillet, etc.).
   * Any other method containing "gauge" / "gaug" unless listed as dimensional above.
   */
  function firIsPassFailGaugeMethod(raw) {
    if (firIsDimensionalMeasuringMethod(raw)) return false;
    var u = String(raw || "").trim().toUpperCase();
    if (!u) return false;
    if (/^FG$|PARALLEL\s*GAU|PERPEND(?:ICULAR|IVULAR)?\s*GAU|SLIP\s*GAU|FEELER|WELD\s*FILLET|SNAP\s*GAU|RING\s*GAU|PLUG\s*GAU|GO\s*NO\s*GO|GO\/NO\s*GO/.test(u)) {
      return true;
    }
    return /\bGAUG(E)?\b/.test(u) || u.indexOf("GAUGE") !== -1 || u.indexOf("GAUG") !== -1;
  }

  function firNormMethodText(raw) {
    return String(raw || "").trim().replace(/\s+/g, " ").toUpperCase();
  }

  /** CMM + Fixture in one method string (any truncation with both tokens). */
  function firIsCmmFixtureComboMethod(raw) {
    var m = firNormMethodText(raw);
    return m.indexOf("CMM") !== -1 && m.indexOf("FIXTURE") !== -1;
  }

  function firIsCmmMethod(raw) {
    var m = firNormMethodText(raw);
    if (firIsCmmFixtureComboMethod(raw)) return false;
    if (m === "CMM") return true;
    if (/^CMM\b/.test(m)) return true;
    if (/COORDINATE\s*MEASURING/.test(m)) return true;
    return false;
  }

  function firIsInspectionFixtureMethod(raw) {
    var m = firNormMethodText(raw);
    if (firIsCmmFixtureComboMethod(raw)) return false;
    if (m.indexOf("INSPECTION FIXTURE") !== -1) return true;
    if (m.indexOf("INSP FIXTURE") !== -1) return true;
    if (m.indexOf("FIXTURE") !== -1 && m.indexOf("CMM") === -1) return true;
    return false;
  }

  function firIsWetLeakTestMethod(raw) {
    return /WET\s*LEAK/.test(firNormMethodText(raw));
  }

  function firIsDryLeakTestMethod(raw) {
    return /DRY\s*LEAK/.test(firNormMethodText(raw));
  }

  function firIsHighPressureLeakTestMethod(raw) {
    return /HIGH\s*PRESSURE\s*LEAK/.test(firNormMethodText(raw));
  }

  /** OK-only shop methods from MOI table (CMM, fixtures, leak tests). */
  function firIsOkOnlyInspectionMethod(raw) {
    if (!String(raw || "").trim()) return false;
    return (
      firIsCmmFixtureComboMethod(raw) ||
      firIsCmmMethod(raw) ||
      firIsInspectionFixtureMethod(raw) ||
      firIsWetLeakTestMethod(raw) ||
      firIsDryLeakTestMethod(raw) ||
      firIsHighPressureLeakTestMethod(raw)
    );
  }

  function firTextIsMillipore(raw) {
    var u = String(raw || "")
      .trim()
      .replace(/\s+/g, " ")
      .toUpperCase();
    if (!u) return false;
    var compact = u.replace(/[\s.\-_/]/g, "");
    return compact === "MILLIPORE" || compact.indexOf("MILLIPORE") !== -1;
  }

  function firIsMilliporeMethod(raw) {
    return firTextIsMillipore(raw);
  }

  function firIsMilliporeParameter(raw) {
    return firTextIsMillipore(raw);
  }

  /** Millipore row when MOI or Parameter names it (e.g. Parameter MILLIPORE + Method WEIGHT MACHIN). */
  function firRowIsMillipore(paramRaw, methodRaw) {
    return firIsMilliporeParameter(paramRaw) || firIsMilliporeMethod(methodRaw);
  }

  function firParseMilliporeSpec(specStr) {
    var s = String(specStr || "").trim();
    if (!s) return null;
    var numMatch = s.match(/-?\d+(?:\.\d+)?/);
    if (!numMatch) return null;
    var limit = parseFloat(numMatch[0]);
    if (isNaN(limit) || limit <= 0) return null;
    var after = s.slice(s.indexOf(numMatch[0]) + numMatch[0].length).trim();
    var unitMatch = after.match(/^([A-Za-zµμ%][A-Za-z0-9µμ.%/\-]*)/);
    var unit = unitMatch ? unitMatch[1] : "";
    return { limit: limit, unit: unit };
  }

  function firParseMilliporeActual(raw) {
    var s = String(raw || "").trim();
    if (!s) return null;
    var achieved = s.match(/achieved\s+(\d+(?:\.\d+)?)/i);
    if (achieved) {
      var n = parseFloat(achieved[1]);
      return isNaN(n) ? null : n;
    }
    var direct = parseFloat(s.replace(/[^\d.]/g, ""));
    return isNaN(direct) ? null : direct;
  }

  function firMilliporePasses(actual, limit) {
    if (actual == null || isNaN(actual) || limit == null || isNaN(limit)) return false;
    return actual < limit;
  }

  function firFormatMilliporeActualDisplay(num, unit) {
    var n = Number(num);
    if (isNaN(n)) return "";
    var text = Number.isInteger(n) ? String(n) : n.toFixed(2);
    var u = String(unit || "").trim();
    if (u) u = u.toUpperCase();
    return u ? text + " " + u : text;
  }

  function firFormatMilliporeMessage(actual, unit) {
    return "Millipore test achieved " + firFormatMilliporeActualDisplay(Number(actual), unit);
  }

  function firRemarksIndicatesPass(raw) {
    var t = String(raw || "").trim();
    if (!t) return false;
    if (t.toUpperCase() === "OK") return true;
    if (/^Millipore\s+test\s+achieved\s+.+/i.test(t) && /found\s+OK\.?$/i.test(t)) return true;
    return false;
  }

  function firSectionBIsNoCpiOnly() {
    var table = document.getElementById("ccp-table");
    if (!table) return true;
    var tbody = table.querySelector("tbody");
    if (!tbody) return true;
    var rows = tbody.querySelectorAll(":scope > tr");
    if (!rows.length) return true;
    return rows.length === 1 && rows[0].classList.contains("fir-no-cpi-row");
  }

  /** Part master may store "NO CPI" as a parameter row — treat as empty Section B. */
  function firIsNoCpiPlaceholderParameter(raw) {
    var p = String(raw || "").trim().replace(/\s+/g, " ").toUpperCase();
    if (!p) return false;
    var compact = p.replace(/[\s.\-_/]/g, "");
    return (
      compact === "NOCPI" ||
      compact === "NOCCP" ||
      compact === "NCCP" ||
      p === "NO CPI" ||
      p === "NO CCP" ||
      p === "N CPI"
    );
  }

  function firIsRealCcpRow(r) {
    if (!r) return false;
    var param = String(r.parameter || "").trim();
    if (!param) return false;
    if (firIsNoCpiPlaceholderParameter(param)) return false;
    return true;
  }

  /** Autofill: strictly below limit, in lower half (≈35–50% of spec). */
  function firRandomMilliporeValue(limit) {
    var lo = limit * 0.35;
    var hi = Math.min(limit * 0.5, limit - 0.01);
    if (hi <= lo) hi = lo;
    var v = lo + Math.random() * (hi - lo);
    v = Math.round(v * 100) / 100;
    if (v >= limit) v = Math.max(lo, Math.round((limit - 0.01) * 100) / 100);
    return v;
  }

  function firIsMilliporeRow(tr) {
    return !!(tr && tr.classList && tr.classList.contains("fir-millipore-row"));
  }

  function firIsNoCpiRow(tr) {
    return !!(tr && tr.classList && tr.classList.contains("fir-no-cpi-row"));
  }

  function firRowTextFromCell(cell) {
    if (!cell) return "";
    var el = cell.querySelector("textarea") || cell.querySelector("input");
    return el ? String(el.value || "").trim() : String(cell.textContent || "").trim();
  }

  function firApplyMilliporeRowLayout(tr) {
    if (!tr || firIsMilliporeRow(tr)) return;
    var cells = tr.querySelectorAll(":scope > td");
    if (cells.length !== 11) return;
    var keepVal = "";
    for (var ci = 5; ci <= 9; ci++) {
      var cellInp = cells[ci].querySelector("input.actual-value") || cells[ci].querySelector('input[type="text"]');
      var v = cellInp ? String(cellInp.value || "").trim() : "";
      if (v && !keepVal) keepVal = v;
    }
    var merged = document.createElement("td");
    merged.colSpan = 5;
    merged.className = "fir-millipore-merged";
    var inp = document.createElement("input");
    inp.type = "text";
    inp.className = "actual-value quali-font millipore-actual";
    inp.value = keepVal;
    merged.appendChild(inp);
    var remarks = cells[10];
    for (var ci = 9; ci >= 5; ci--) cells[ci].remove();
    tr.insertBefore(merged, remarks);
    tr.classList.add("fir-millipore-row");
  }

  function firUnmergeMilliporeRow(tr) {
    if (!tr || !firIsMilliporeRow(tr)) return;
    var cells = tr.querySelectorAll(":scope > td");
    if (cells.length !== 7) return;
    var merged = cells[5];
    var val = "";
    var inp = merged.querySelector("input");
    if (inp) val = inp.value;
    var numOnly = firParseMilliporeActual(val);
    var restore = numOnly != null ? String(numOnly) : String(val || "").replace(/^Millipore\s+test\s+achieved\s+/i, "").trim();
    var remarks = cells[6];
    merged.remove();
    for (var i = 0; i < 5; i++) {
      var td = document.createElement("td");
      var input = document.createElement("input");
      input.type = "text";
      input.className = "actual-value quali-font";
      if (i === 0) {
        input.value = restore && !/^Millipore/i.test(restore) ? restore : (numOnly != null ? String(numOnly) : "");
      }
      td.appendChild(input);
      tr.insertBefore(td, remarks);
    }
    tr.classList.remove("fir-millipore-row");
  }

  function firSyncMilliporeRowLayout(tr) {
    if (!tr || firIsNoCpiRow(tr)) return;
    var cells = tr.querySelectorAll(":scope > td");
    if (cells.length < 5) return;
    var paramEl = cells[1].querySelector("textarea") || cells[1].querySelector("input");
    var methodEl = firQueryMethodInput(cells[4]);
    var param = paramEl ? String(paramEl.value || "").trim() : "";
    var method = methodEl ? String(methodEl.value || "").trim() : "";
    if (firRowIsMillipore(param, method)) {
      firApplyMilliporeRowLayout(tr);
    } else {
      firUnmergeMilliporeRow(tr);
    }
  }

  function firSyncAllMilliporeRowLayouts() {
    ["dimension-table", "ccp-table", "coating-table"].forEach(function(tableId) {
      var table = document.getElementById(tableId);
      if (!table) return;
      table.querySelectorAll("tbody tr").forEach(function(tr) {
        firSyncMilliporeRowLayout(tr);
      });
    });
  }

  function firIsQualitativeMeasuredMethod(raw) {
    return (
      firIsVisualMethod(raw) ||
      firIsQrScannerMethod(raw) ||
      firIsThreadPlugGaugeMethod(raw) ||
      firIsPassFailGaugeMethod(raw)
    );
  }

  /**
   * Metric thread / bolt designation — M8, M6X1, M8X1.25, M8X1.25X35 (size × pitch × length).
   * Checked with thread plug gauge (TPG): measured values are OK only.
   */
  function firIsMetricThreadSpecification(specRaw) {
    var s = String(specRaw || "")
      .trim()
      .toUpperCase()
      .replace(/\s+/g, "");
    if (!s) return false;
    // M8 / M8X1.25 / M8X1.25X35 (optional pitch and length)
    if (/^M\d+(\.\d+)?([X×]\d+(\.\d+)?){0,2}$/.test(s)) return true;
    // Embedded designation e.g. "THREAD M8X1.25" or "M8X1.25X35 LG"
    if (/\bM\d+(\.\d+)?([X×]\d+(\.\d+)?){1,2}\b/.test(s)) return true;
    if (/^M\d+(\.\d+)?\b/.test(s)) return true;
    return false;
  }

  /** Pass/fail measured cells from parameter + specification + method together. */
  function firRowUsesQualitativeMeasured(paramRaw, specRaw, methodRaw) {
    var method = String(methodRaw || "").trim();
    var spec = String(specRaw || "").trim();
    var param = String(paramRaw || "").trim();
    if (firRowIsMillipore(param, method)) return false;
    if (firIsOkOnlyInspectionMethod(method)) return true;
    if (firIsQrCodeParameter(param) || firIsQrScannerMethod(method)) return true;
    if (firGdtParameterUsesQualitativeMeasured(param, method)) return true;
    if (firIsFeelerGaugeMethod(method) || firIsParallelGaugeMethod(method) || firIsPerpendicularGaugeMethod(method)) return true;
    if (firIsQualitativeMeasuredMethod(method)) return true;
    if (firIsMetricThreadSpecification(spec)) return true;
    if (firIsVisualMethod(method) || (firIsVisualSpecification(spec) && (firIsVisualParameter(param) || firIsVisualMethod(method)))) {
      return true;
    }
    return false;
  }

  /**
   * Resolve how a row fills measured values: parameter + specification + method are correlated.
   * Returns { mode: 'qualitative' | 'numeric' | 'none', range?, param?, spec?, method? }
   */
  function firResolveRowMeasuredContext(paramRaw, specRaw, methodRaw) {
    var param = String(paramRaw || "").trim();
    var spec = String(specRaw || "").trim();
    var method = String(methodRaw || "").trim();
    var ctx = { param: param, spec: spec, method: method };

    if (firRowIsMillipore(param, method)) {
      var mp = firParseMilliporeSpec(spec);
      if (mp) {
        return Object.assign({ mode: "millipore", limit: mp.limit, unit: mp.unit }, ctx);
      }
    }

    if (firRowUsesQualitativeMeasured(param, spec, method)) {
      return Object.assign({ mode: "qualitative" }, ctx);
    }

    var range = parseSpec(spec);
    if (!range) {
      return Object.assign({ mode: "none" }, ctx);
    }

    if (firIsDftStyleRow(param, spec, method)) {
      range = Object.assign({}, range, { step: 0.1, oneDecimal: true });
    }
    if (range.limitFromZero) {
      var limitStep = firInstrumentResolutionStep(method);
      range = Object.assign({}, range, { step: limitStep, limitResolution: limitStep });
    }
    if (range.isAngle || /^BP$|^B\.P\.?$/i.test(method)) {
      range = Object.assign({}, range, { isAngle: true });
    }

    return Object.assign({ mode: "numeric", range: range }, ctx);
  }

  function firFillQualitativeMeasuredRow(tr) {
    if (firIsNoCpiRow(tr) || firIsMilliporeRow(tr)) return;
    var cells = tr.querySelectorAll(":scope > td");
    if (cells.length < 11) return;
    var remarksEl = cells[10].querySelector("input.remarks-value") || cells[10].querySelector("input");
    if (!remarksEl) return;
    var nActiveQ = firGetMeasuredColumnCount();
    for (var ci = 5; ci <= 9; ci++) {
      var td = cells[ci];
      if (!td) continue;
      var inp = td.querySelector("input.actual-value") || td.querySelector('input[type="text"]');
      if (!inp) continue;
      if (inp.disabled) {
        inp.value = "";
        continue;
      }
      inp.value = ci < 5 + nActiveQ ? "OK" : "";
    }
    remarksEl.value = "OK";
    updateStatusButtons();
  }

  function firRefreshQualitativeMeasuredCellsInTables() {
    var root = document.getElementById("reportRoot");
    if (!root) return;
    root.querySelectorAll("#dimension-table tbody tr, #ccp-table tbody tr, #coating-table tbody tr").forEach(function(tr) {
      if (firIsNoCpiRow(tr) || firIsMilliporeRow(tr)) return;
      var cells = tr.querySelectorAll(":scope > td");
      if (cells.length < 11) return;
      var mel = firQueryMethodInput(cells[4]);
      var specEl = cells[2].querySelector("textarea") || cells[2].querySelector("input");
      if (!mel) return;
      var specRaw = specEl ? (specEl.value || "").trim() : "";
      if (firRowUsesQualitativeMeasured(
        cells[1].querySelector("textarea") || cells[1].querySelector("input") ? (cells[1].querySelector("textarea") || cells[1].querySelector("input")).value : "",
        specRaw,
        (mel.value || "").trim()
      )) {
        firUpdateRowRemarksFromMeasurements(tr);
      }
    });
  }

  /** After sample size changes: refill OK columns for Visual / pass-fail gauge / TPG / M#X# thread rows (no preload on initial page load). */
  function firInitQualitativeMeasuredRows() {
    firRefreshQualitativeMeasuredCellsInTables();
  }

  function firOnSampleSizeOrColumnsChanged() {
    firApplyMeasuredColumnAvailability();
    firInitQualitativeMeasuredRows();
    updateStatusButtons();
  }

  function esc(s) {
    if (s == null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /** Excel-like wrap: grow textarea height to fit wrapped Parameter / Specification text. */
  function firAutosizeTextarea(el) {
    if (!el || el.tagName !== "TEXTAREA") return;
    el.style.height = "auto";
    el.style.height = Math.max(el.scrollHeight, 18) + "px";
  }

  function firAutosizeAllTextareas(root) {
    root = root || document.getElementById("reportRoot");
    if (!root) return;
    root.querySelectorAll("textarea").forEach(firAutosizeTextarea);
  }

  function firQueryMethodInput(container) {
    if (!container) return null;
    return container.querySelector("textarea.method-input, input.method-input");
  }

  function firAttrUrl(u) {
    if (u == null || u === undefined || u === '') return '';
    return String(u).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
  }

  function firSpecialCharTag(raw) {
    var t = (raw == null || raw === undefined) ? '' : String(raw).trim().toLowerCase();
    if (t === 'critical') return 'Critical';
    if (t === 'safety') return 'Safety';
    if (t === 'important') return 'Important';
    return '';
  }

  function firSpecialCharImgUrl(tag) {
    if (!globalSettings) return '';
    if (tag === 'Critical') return globalSettings.char_critical_path || '';
    if (tag === 'Safety') return globalSettings.char_safety_path || '';
    if (tag === 'Important') return globalSettings.char_important_path || '';
    return '';
  }

  function firRowSlNo(row, counter) {
    if (row && row.sl_no != null && row.sl_no !== "") {
      var n = parseInt(row.sl_no, 10);
      if (!isNaN(n) && n > 0) return n;
    }
    return counter;
  }

  function firAdvanceSlNo(row, counter) {
    var sn = firRowSlNo(row, counter);
    return Math.max(counter, sn + 1);
  }

  if (!partName || !description) {
    document.body.innerHTML = `<h2 style='text-align:center;color:red;'>Missing part data. Please go back and fill the form.</h2>
    <div style='text-align:center;'><button onclick='history.back()'>Go Back</button></div>`;
  } else {
    let html = ``;
    let slno = 1;
    const root = document.getElementById('reportRoot');

    html += `<div class='report-container'>`;
    html += `
      <table class="header-table">
        <tr>
          <td rowspan="2" colspan="5" class="logo-cell" id="companyCode"></td>
          <td colspan="7" class="header-title">FINAL INSPECTION REPORT</td>
          <td colspan="4" class="small-cell" id="docInfo"></td>
        </tr><tr></tr>
        <tr><td class="bold" colspan="2">VENDOR CODE :</td><td colspan="3"><input type="text" value="${vendorCode}"></td>
        <td class="bold" colspan="2">CUSTOMER</td><td colspan="4"><input type="text" value="${customer}"></td>
        <td class="bold" colspan="2">REPORT NO :</td><td colspan="3"><input type="text" value="${reportNo}"></td></tr>
        <tr><td class="bold" colspan="2">PART NO :</td><td colspan="3"><input type="text" value="${partName}"></td>
        <td class="bold" colspan="2">LOT QTY :</td><td colspan="4"><input type="text" value="${lotQty}"></td>
        <td class="bold" colspan="2">INVOICE NO :</td><td colspan="3"><input type="text" value="${invoiceNo}"></td></tr>
        <tr><td class="bold" colspan="2">DESCRIPTION :</td><td colspan="3"><textarea rows="1" class="fir-wrap-cell">${esc(description)}</textarea></td>
        <td class="bold" colspan="2">SAMPLE SIZE :</td><td colspan="4"><input type="text" id="firSampleSizeInput" value="${sampleSize}"></td>
        <td class="bold" colspan="2">DATE :</td><td colspan="3"><input type="text" value="${reportDate}"></td></tr>
        <tr><td class="bold" colspan="2">DRAW.REV NO :</td><td colspan="14"><input type="text" value="${drawRev}"></td></tr>
      </table>`;

    html += `<div class="section-title">A) Dimension Parameters</div>`;
    html += `
      <table class="data-table" id="dimension-table"><thead>
        <tr><th rowspan="2" style="width:5%;">Sl No</th>
        <th rowspan="2" style="width:15%;">Parameter</th>
        <th rowspan="2" style="width:15%;">Specification</th>
        <th rowspan="2" style="width:5%;">Special Char.</th>
        <th rowspan="2" style="width:10%;">Method of Inspection</th>
        <th colspan="5" style="width:41%;" class="fir-col-head">Actual Measured Values</th>
        <th rowspan="2" style="width:8%;">Remarks</th></tr>
        <tr><th class="fir-col-head-num">1</th><th class="fir-col-head-num">2</th>
        <th class="fir-col-head-num">3</th><th class="fir-col-head-num">4</th><th class="fir-col-head-num">5</th></tr>
      </thead><tbody>`;

    const actualInput = '<input type="text" class="actual-value quali-font">';
    const remarksInput = '<input type="text" class="remarks-value quali-font">';
    const wrapCell = (val) => `<textarea rows="1" class="fir-wrap-cell">${esc(val || '')}</textarea>`;
    const shortInput = (val) => `<input type="text" value="${esc(val || '')}">`;
    const methodInput = (val) => `<textarea rows="1" class="method-input fir-wrap-cell">${esc(val || '')}</textarea>`;
    /** Part-master special_char only: no dropdown/edit on FIR preview. Icon if C/S/I + image in settings; else plain text. */
    const specialCharCell = (val) => {
      var raw = (val == null || val === undefined) ? '' : String(val).trim();
      var tag = firSpecialCharTag(val);
      var imgUrl = firSpecialCharImgUrl(tag);
      var chunks = [];
      if (imgUrl) {
        chunks.push(
          '<img class="fir-special-char-icon" alt="" src="' +
            firAttrUrl(imgUrl) +
            '" style="max-height:36px;max-width:100%;object-fit:contain;display:block;margin:0 auto;" />',
        );
      } else if (tag) {
        chunks.push('<div class="fir-special-char-text">' + esc(tag) + '</div>');
      } else if (raw) {
        chunks.push('<div class="fir-special-char-text">' + esc(raw) + '</div>');
      }
      var inner = chunks.length ? chunks.join('') : '&nbsp;';
      return '<div class="fir-special-char-box fir-special-char-static">' + inner + '</div>';
    };
    for (let i = 1; i <= totalRows; i++) {
      const idx = i - 1;
      const row = FIR_SPEC_DATA[idx];
      if (row) {
        var snA = firRowSlNo(row, slno);
        slno = firAdvanceSlNo(row, slno);
        html += `<tr><td>${snA}</td><td>${wrapCell(row.parameter)}</td><td>${wrapCell(row.specification)}</td><td>${specialCharCell(row.special_char)}</td><td>${methodInput(row.method_of_inspection)}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${remarksInput}</td></tr>`;
      } else {
        html += `<tr><td>${slno++}</td><td>${wrapCell()}</td><td>${wrapCell()}</td><td>${specialCharCell()}</td><td>${methodInput()}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${remarksInput}</td></tr>`;
      }
    }
    html += `</tbody></table>`;

    {
        const actualInput = '<input type="text" class="actual-value quali-font">';
        const remarksInput = '<input type="text" class="remarks-value quali-font">';
        let bHtml = '<div class="section-title">B) Customer End Complaints Parameters & Check Points</div><table class="data-table" id="ccp-table"><thead><tr><th rowspan="2" style="width:5%;">Sl No</th><th rowspan="2" style="width:15%;">Parameter</th><th rowspan="2" style="width:15%;">Specification</th><th rowspan="2" style="width:5%;">Special Char.</th><th rowspan="2" style="width:10%;">Method</th><th colspan="5" style="width:41%;" class="fir-col-head">Actual Measured Values</th><th rowspan="2" style="width:8%;">Remarks</th></tr><tr><th class="fir-col-head-num">1</th><th class="fir-col-head-num">2</th><th class="fir-col-head-num">3</th><th class="fir-col-head-num">4</th><th class="fir-col-head-num">5</th></tr></thead><tbody>';
        var ccpRows = (FIR_CCP_DATA || []).filter(firIsRealCcpRow);
        if (ccpRows.length > 0) {
          ccpRows.forEach(function(r) {
            var snB = firRowSlNo(r, slno);
            slno = firAdvanceSlNo(r, slno);
            bHtml += `<tr><td style="width:5%;">${snB}</td><td>${wrapCell(r.parameter)}</td><td>${wrapCell(r.specification)}</td><td>${specialCharCell(r.special_char)}</td><td>${methodInput(r.method_of_inspection)}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${remarksInput}</td></tr>`;
          });
        } else {
          bHtml +=
            '<tr class="fir-no-cpi-row"><td style="width:5%;">' +
            slno++ +
            '</td><td colspan="10" class="fir-no-cpi-merged"><span class="fir-no-cpi-value quali-font">No CPI</span></td></tr>';
        }
        bHtml += '</tbody></table>';
        const cRemarksInput = '<input type="text" class="remarks-value quali-font" value="OK">';
        let cHtml = '<div class="section-title">C) Material Grade</div><table class="data-table" id="material-table"><tbody>';
        if (FIR_MATERIAL_DATA.length > 0) {
          FIR_MATERIAL_DATA.forEach(function(r) {
            var snC = firRowSlNo(r, slno);
            slno = firAdvanceSlNo(r, slno);
            cHtml += `<tr><td style="width:5%;">${snC}</td><td style="width:85%;">${wrapCell(r.material_grade)}</td><td style="width:10%;">${cRemarksInput}</td></tr>`;
          });
        } else {
          cHtml += `<tr><td style="width:5%;">${slno++}</td><td style="width:85%;">${wrapCell()}</td><td style="width:10%;">${cRemarksInput}</td></tr>`;
        }
        cHtml += '</tbody></table>';
        let dHtml = '<div class="section-title">D) Surface Coating</div><table class="data-table" id="coating-table"><thead><tr><th rowspan="2" style="width:5%;">Sl No</th><th rowspan="2" style="width:15%;">Parameter</th><th rowspan="2" style="width:15%;">Specification</th><th rowspan="2" style="width:5%;">Special Char.</th><th rowspan="2" style="width:10%;">Method</th><th colspan="5" style="width:41%;" class="fir-col-head">Actual Measured Values</th><th rowspan="2" style="width:8%;">Remarks</th></tr><tr><th class="fir-col-head-num">1</th><th class="fir-col-head-num">2</th><th class="fir-col-head-num">3</th><th class="fir-col-head-num">4</th><th class="fir-col-head-num">5</th></tr></thead><tbody>';
        if (FIR_COATING_DATA.length > 0) {
          FIR_COATING_DATA.forEach(function(r) {
            var snD = firRowSlNo(r, slno);
            slno = firAdvanceSlNo(r, slno);
            dHtml += `<tr><td>${snD}</td><td>${wrapCell(r.parameter)}</td><td>${wrapCell(r.specification)}</td><td>${specialCharCell(r.special_char)}</td><td>${methodInput(r.method_of_inspection)}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${remarksInput}</td></tr>`;
          });
        } else {
          dHtml += `<tr><td>${slno++}</td><td>${wrapCell()}</td><td>${wrapCell()}</td><td>${specialCharCell()}</td><td>${methodInput()}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${actualInput}</td><td>${remarksInput}</td></tr>`;
        }
        dHtml += '</tbody></table>';
        html += bHtml + cHtml + dHtml;
    }

    html += `
        <table class="data-table signatures-section" style="margin-top:0; table-layout:fixed;">
          <tr class="fir-signature-row">
            <td class="bold">Inspector Name & Sign:</td>
            <td class="signature-cell"><div class="signature-container">
              <img id="signaturePreview" class="signature-preview"></div></td>
            <td class="section-title">Status of Inspection:</td><td id="status-accepted" class="status-btn" colspan="2">Accepted</td><td id="status-rejected" class="status-btn" style="display:none;" colspan="2">Rejected</td>
            <td class="section-title">AL SQE Verification</td><td><input type="text"></td>
            <td class="section-title fir-sampling-plan-label" rowspan="2">Sampling Plan</td>
            <td class="fir-sampling-plan-cell" rowspan="2" colspan="2">
              <table class="fir-sampling-inner">
                <tr><td class="section-title fir-sampling-label">Customer Complaint Parameter</td><td>100% Inspection</td></tr>
                <tr><td class="section-title fir-sampling-label">Dimension Parameter</td><td>Minimum 5 Nos</td></tr>
                <tr><td class="section-title fir-sampling-label">Visual Check</td><td>100% Inspection</td></tr>
              </table>
            </td></tr>
          <tr class="fir-signature-row">
            <td class="bold">Quality Head Name & Sign:</td>
            <td class="signature-cell"><div class="signature-container">
              <img id="qSignaturePreview" class="signature-preview"></div></td>
            <td colspan="5" class="fir-signature-spacer">&nbsp;</td>
          </tr>
        </table>`;
    html += `</div>`;
    root.innerHTML = "";
    root.insertAdjacentHTML('beforeend', html);
    /* Remove legacy "Special characteristic symbols (reference)" legend (any nesting; old/cached builds). */
    try {
      var _rc = root.querySelector('.report-container');
      if (_rc) {
        _rc.querySelectorAll('div').forEach(function (el) {
          if (el.closest('#dimension-table')) return;
          if (el.closest('table.header-table')) return;
          var _t = ((el.textContent || '') + '').replace(/\s+/g, ' ').toLowerCase();
          if (_t.indexOf('special characteristic symbols') !== -1 && _t.indexOf('reference') !== -1) {
            el.remove();
          }
        });
      }
    } catch (_e) { /* ignore */ }

    // Apply global settings: logo, company name, and document meta
    const companyCell = root.querySelector('#companyCode');
    if (companyCell && globalSettings) {
      let inner = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;">';
      if (globalSettings.logo_path) {
        inner += `<div style="width:90px;height:90px;border:1px solid #000;overflow:hidden;margin-bottom:4px;display:flex;align-items:center;justify-content:center;background:#fff;"><img class="fir-logo-img" src="${globalSettings.logo_path}" style="width:100%;height:100%;object-fit:cover;" alt=""></div>`;
      }
      if (globalSettings.company_name) {
        inner += `<div style="font-weight:bold;font-style:italic;text-align:center;">${globalSettings.company_name}</div>`;
      }
      inner += '</div>';
      companyCell.innerHTML = inner;
    }
    const docInfoCell = root.querySelector('#docInfo');
    if (docInfoCell && globalSettings) {
      const lines = [];
      if (globalSettings.format_no) lines.push(`Format No: ${globalSettings.format_no}`);
      if (globalSettings.issue_date) lines.push(`Issue Dt: ${globalSettings.issue_date}`);
      if (globalSettings.doc_rev_no) lines.push(`Doc Rev No: ${globalSettings.doc_rev_no}`);
      if (globalSettings.rev_date) lines.push(`Rev Dt: ${globalSettings.rev_date}`);
      docInfoCell.innerHTML = lines.join('<br>');
    }
    /* Column enable/disable only on first paint — do not pre-fill TPG/Visual OK until user clicks Autofill. */
    firApplyMeasuredColumnAvailability();
    firSyncAllMilliporeRowLayouts();
    document.querySelectorAll("tr.fir-millipore-row").forEach(function(tr) {
      firUpdateRowRemarksFromMeasurements(tr);
    });
    firAutosizeAllTextareas(root);
    requestAnimationFrame(function() {
      firAutosizeAllTextareas(root);
    });
    var firSampleEl = document.getElementById("firSampleSizeInput");
    if (firSampleEl) {
      firSampleEl.addEventListener("input", firOnSampleSizeOrColumnsChanged);
      firSampleEl.addEventListener("change", firOnSampleSizeOrColumnsChanged);
    }
  }

  // Apply global signatures (from settings)
  if (globalSettings) {
    const insp = document.getElementById('signaturePreview');
    if (insp && globalSettings.inspector_signature_path) {
      insp.src = globalSettings.inspector_signature_path;
      insp.style.display = 'block';
    }
    const qual = document.getElementById('qSignaturePreview');
    if (qual && globalSettings.quality_signature_path) {
      qual.src = globalSettings.quality_signature_path;
      qual.style.display = 'block';
    }
  }

  function updateStatusButtons() {
    try {
      const acceptedEl = document.getElementById('status-accepted');
      const rejectedEl = document.getElementById('status-rejected');
      if (!acceptedEl || !rejectedEl) return;
      const remarksInputs = document.querySelectorAll('input.remarks-value');
      let allOk = true;
      let hasRemarks = false;
      remarksInputs.forEach(function(inp) {
        const v = (inp.value || '').trim();
        if (v !== '') hasRemarks = true;
        if (v !== '' && !firRemarksIndicatesPass(v)) allOk = false;
      });
      if (hasRemarks && !allOk) {
        acceptedEl.style.display = 'none';
        acceptedEl.colSpan = 2;
        rejectedEl.style.display = 'table-cell';
        rejectedEl.colSpan = 4;
        rejectedEl.classList.add('highlight');
      } else {
        acceptedEl.style.display = 'table-cell';
        acceptedEl.colSpan = 4;
        rejectedEl.style.display = 'none';
        rejectedEl.colSpan = 2;
        rejectedEl.classList.remove('highlight');
        acceptedEl.classList.toggle('highlight', hasRemarks && allOk);
      }
    } catch (err) { console.error('updateStatusButtons', err); }
  }
  try {
    updateStatusButtons();
    var rootEl = document.getElementById('reportRoot');
    if (rootEl) {
      rootEl.addEventListener('input', function(e) {
        if (e.target && e.target.classList && e.target.classList.contains('remarks-value')) updateStatusButtons();
        if (e.target && e.target.classList && e.target.classList.contains('method-input')) {
          var trM = e.target.closest('tr');
          if (trM) {
            firSyncMilliporeRowLayout(trM);
            var cellsM = trM.querySelectorAll(":scope > td");
            if (firIsMilliporeRow(trM)) {
              firUpdateRowRemarksFromMeasurements(trM);
              return;
            }
            var paramElM = cellsM[1] ? (cellsM[1].querySelector("textarea") || cellsM[1].querySelector("input")) : null;
            var specElM = cellsM[2] ? (cellsM[2].querySelector("textarea") || cellsM[2].querySelector("input")) : null;
            var paramM = paramElM ? (paramElM.value || "").trim() : "";
            var specM = specElM ? (specElM.value || "").trim() : "";
            var methodM = (e.target.value || "").trim();
            if (firRowUsesQualitativeMeasured(paramM, specM, methodM)) {
              firFillQualitativeMeasuredRow(trM);
            } else {
              for (var ciM = 5; ciM <= 9; ciM++) {
                var tdM = cellsM[ciM];
                if (!tdM) continue;
                var inpM = tdM.querySelector("input.actual-value") || tdM.querySelector('input[type="text"]');
                if (inpM && !inpM.disabled && (inpM.value || "").trim().toUpperCase() === "OK") inpM.value = "";
              }
            }
            firUpdateRowRemarksFromMeasurements(trM);
          }
        }
        if (e.target && e.target.tagName === 'TEXTAREA') {
          firAutosizeTextarea(e.target);
          var trTa = e.target.closest('tr');
          if (trTa) {
            firSyncMilliporeRowLayout(trTa);
            firUpdateRowRemarksFromMeasurements(trTa);
          }
        }
        if (e.target && e.target.classList && e.target.classList.contains('actual-value')) {
          var tr = e.target.closest('tr');
          if (tr) {
            if (firIsMilliporeRow(tr) && e.target.classList.contains('millipore-actual')) {
              firUpdateRowRemarksFromMeasurements(tr);
            } else if (!firIsMilliporeRow(tr)) {
              firUpdateRowRemarksFromMeasurements(tr);
            }
          }
        }
      });
      rootEl.addEventListener('change', function(e) {
        if (e.target && e.target.classList && e.target.classList.contains('remarks-value')) updateStatusButtons();
        if (e.target && e.target.classList && e.target.classList.contains('method-input')) {
          var trM2 = e.target.closest('tr');
          if (trM2) {
            firSyncMilliporeRowLayout(trM2);
            var cellsM2 = trM2.querySelectorAll(":scope > td");
            if (firIsMilliporeRow(trM2)) {
              firUpdateRowRemarksFromMeasurements(trM2);
              return;
            }
            var paramElM2 = cellsM2[1] ? (cellsM2[1].querySelector("textarea") || cellsM2[1].querySelector("input")) : null;
            var specElM2 = cellsM2[2] ? (cellsM2[2].querySelector("textarea") || cellsM2[2].querySelector("input")) : null;
            var paramM2 = paramElM2 ? (paramElM2.value || "").trim() : "";
            var specM2 = specElM2 ? (specElM2.value || "").trim() : "";
            var methodM2 = (e.target.value || "").trim();
            if (firRowUsesQualitativeMeasured(paramM2, specM2, methodM2)) {
              firFillQualitativeMeasuredRow(trM2);
            } else {
              for (var ciM2 = 5; ciM2 <= 9; ciM2++) {
                var tdM2 = cellsM2[ciM2];
                if (!tdM2) continue;
                var inpM2 = tdM2.querySelector("input.actual-value") || tdM2.querySelector('input[type="text"]');
                if (inpM2 && !inpM2.disabled && (inpM2.value || "").trim().toUpperCase() === "OK") inpM2.value = "";
              }
            }
            firUpdateRowRemarksFromMeasurements(trM2);
          }
        }
        if (e.target && e.target.tagName === 'TEXTAREA') {
          firAutosizeTextarea(e.target);
          var trTa2 = e.target.closest('tr');
          if (trTa2) {
            firSyncMilliporeRowLayout(trTa2);
            firUpdateRowRemarksFromMeasurements(trTa2);
          }
        }
        if (e.target && e.target.classList && e.target.classList.contains('actual-value')) {
          var tr2 = e.target.closest('tr');
          if (tr2) {
            if (firIsMilliporeRow(tr2) && e.target.classList.contains('millipore-actual')) {
              firUpdateRowRemarksFromMeasurements(tr2);
            } else if (!firIsMilliporeRow(tr2)) {
              firUpdateRowRemarksFromMeasurements(tr2);
            }
          }
        }
      });
    }
  } catch (err) { console.error('status/root init', err); }

  // --- Parse specification → min/max for autofill and remarks (explicit tolerance only; bare value = 0…limit) ---
  function firDecimalPlacesFromString(str) {
    var s = String(str == null ? "" : str).trim();
    var dot = s.indexOf(".");
    if (dot === -1) return 0;
    return s.length - dot - 1;
  }

  /** Avoid 6.35+0.1 → 6.449999… so boundary values like 6.45 still pass. */
  function firSnapToleranceBounds(nominal, tol, min, max) {
    var prec = Math.max(
      firDecimalPlacesFromString(nominal),
      firDecimalPlacesFromString(tol),
      2
    );
    return {
      min: firRoundToDecimals(min, prec),
      max: firRoundToDecimals(max, prec),
      precision: prec,
    };
  }

  function parseSpec(specStr) {
    const s = (specStr || "").trim();
    if (!s) return null;
    if (firIsMetricThreadSpecification(s)) return null;
    const isRadius = /R\s*\d/i.test(s);
    const isAngle = /°|\bdeg(?:ree)?s?\b/i.test(s);

    // "96.91/97.16" or "95.5/96" → allowable range [min, max] (order-independent).
    // Do not use \\b — in JS the dot in 95.5 is non-word, so \\b can match "5/96" instead of "95.5/96".
    const slashRange = s.match(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/);
    if (slashRange) {
      const a = parseFloat(slashRange[1]);
      const b = parseFloat(slashRange[2]);
      if (!isNaN(a) && !isNaN(b)) {
        const lo = Math.min(a, b);
        const hi = Math.max(a, b);
        const nominal = (lo + hi) / 2;
        return { min: lo, max: hi, nominal, step: isRadius ? 0.5 : null, isRadius, isAngle };
      }
    }

    // "95.5 - 96" / "95.5 to 96" explicit limits (not ± tolerance)
    if (!/±/.test(s)) {
      const dashRange = s.match(/^(\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?)\s*$/i);
      if (dashRange) {
        const a = parseFloat(dashRange[1]);
        const b = parseFloat(dashRange[2]);
        if (!isNaN(a) && !isNaN(b)) {
          const lo = Math.min(a, b);
          const hi = Math.max(a, b);
          return { min: lo, max: hi, nominal: (lo + hi) / 2, step: isRadius ? 0.5 : null, isRadius, isAngle };
        }
      }
    }

    // "8 – 12 µm", "8-12 micron", "8 to 12 µm" → explicit micron acceptance band
    const micronRange = s.match(/\b([0-9]+(?:\.[0-9]+)?)\s*(?:[-–—]|to)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:µm|um|micron|microns)\b/i);
    if (micronRange) {
      var loM = parseFloat(micronRange[1]);
      var hiM = parseFloat(micronRange[2]);
      if (!isNaN(loM) && !isNaN(hiM)) {
        var loMic = Math.min(loM, hiM);
        var hiMic = Math.max(loM, hiM);
        return {
          min: loMic,
          max: hiMic,
          nominal: (loMic + hiMic) / 2,
          step: 0.1,
          oneDecimal: true,
          isRadius: false,
          isAngle: false,
        };
      }
    }

    // "Min 12 micron" / "Max 12 micron" — miswritten lone limit; plating band is (upper − 4)…upper µm
    const minMaxMicron = s.match(/^\s*(?:min\.?|minimum|max\.?|maximum)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:µm|um|micron|microns|mic)?\s*$/i);
    if (minMaxMicron) {
      var upperMic = parseFloat(minMaxMicron[1]);
      if (!isNaN(upperMic)) {
        var lowerMic = Math.max(0, upperMic - 4);
        return {
          min: lowerMic,
          max: upperMic,
          nominal: (lowerMic + upperMic) / 2,
          step: 0.1,
          oneDecimal: true,
          isRadius: false,
          isAngle: false,
        };
      }
    }

    const rBand = s.match(/R\s*([0-9]+(?:\.[0-9]+)?)\s*(?:±|\+\/-)\s*R?\s*([0-9]+(?:\.[0-9]+)?)/i);
    if (rBand) {
      const nominalR = parseFloat(rBand[1]);
      const tolR = parseFloat(rBand[2]);
      if (!isNaN(nominalR) && !isNaN(tolR)) {
        return {
          min: nominalR - tolR,
          max: nominalR + tolR,
          nominal: nominalR,
          step: 0.5,
          isRadius: true,
          isAngle,
        };
      }
    }

    const numStr = s.replace(/[^\d.\s±+-]/g, " ").trim();
    const numbers = numStr.match(/-?\d+\.?\d*/g);
    if (!numbers || numbers.length === 0) return null;
    const nominal = parseFloat(numbers[0]);
    if (isNaN(nominal)) return null;
    let min = nominal, max = nominal;
    var limitFromZero = false;
    var comparePrecision = 2;
    const plusMinus = s.match(/±\s*([0-9.]+)/i);
    const plusMinusAscii = s.match(/\+\s*\/\s*-\s*([0-9.]+)/);
    const plusOnly = s.match(/\+\s*([0-9.]+)/);
    const minusOnly = plusMinusAscii ? null : s.match(/-(\s*[0-9.]+)/);
    if (plusMinus) {
      const tol = parseFloat(plusMinus[1]);
      if (!isNaN(tol)) {
        var snappedPm = firSnapToleranceBounds(nominal, tol, nominal - tol, nominal + tol);
        min = snappedPm.min;
        max = snappedPm.max;
        comparePrecision = snappedPm.precision;
      }
    } else if (plusMinusAscii) {
      const tol = parseFloat(plusMinusAscii[1]);
      if (!isNaN(tol)) {
        var snappedPa = firSnapToleranceBounds(nominal, tol, nominal - tol, nominal + tol);
        min = snappedPa.min;
        max = snappedPa.max;
        comparePrecision = snappedPa.precision;
      }
    } else if (plusOnly && minusOnly) {
      const upper = parseFloat(plusOnly[1]);
      const lower = parseFloat(minusOnly[1].trim());
      if (!isNaN(upper)) max = firRoundToDecimals(nominal + upper, Math.max(firDecimalPlacesFromString(nominal), firDecimalPlacesFromString(plusOnly[1]), 2));
      if (!isNaN(lower)) min = firRoundToDecimals(nominal - lower, Math.max(firDecimalPlacesFromString(nominal), firDecimalPlacesFromString(minusOnly[1]), 2));
      comparePrecision = Math.max(firDecimalPlacesFromString(min), firDecimalPlacesFromString(max), 2);
    } else if (plusOnly) {
      const upper = parseFloat(plusOnly[1]);
      if (!isNaN(upper)) {
        max = firRoundToDecimals(nominal + upper, Math.max(firDecimalPlacesFromString(nominal), firDecimalPlacesFromString(plusOnly[1]), 2));
        comparePrecision = Math.max(firDecimalPlacesFromString(nominal), firDecimalPlacesFromString(plusOnly[1]), 2);
      }
    } else if (minusOnly) {
      const lower = parseFloat(minusOnly[1].trim());
      if (!isNaN(lower)) {
        min = firRoundToDecimals(nominal - lower, Math.max(firDecimalPlacesFromString(nominal), firDecimalPlacesFromString(minusOnly[1]), 2));
        comparePrecision = Math.max(firDecimalPlacesFromString(nominal), firDecimalPlacesFromString(minusOnly[1]), 2);
      }
    } else if (isRadius) {
      // Plain R## in spec (no ± shown): default bands — < R5 → ±0.5, R5 and above → ±1
      const tol = nominal < 5 ? 0.5 : 1;
      min = nominal - tol;
      max = nominal + tol;
    } else {
      // Bare numeric limit only (e.g. flatness 0.5, parallelism 1): 0 ≤ measured ≤ value — never ±10% or other implicit band.
      min = 0;
      max = Math.max(0, nominal);
      limitFromZero = true;
    }
    return { min, max, nominal, step: isRadius ? 0.5 : null, isRadius, isAngle, limitFromZero, precision: comparePrecision };
  }

  /**
   * Shop-floor instrument resolution (mm) for limit-only specs — avoids autofill like 0.043 when the gauge reads 0.01.
   * Derived from Method of Inspection text; default 0.01 mm when unknown.
   */
  function firInstrumentResolutionStep(methodRaw) {
    var raw = String(methodRaw || "").trim();
    var m = raw.toUpperCase();
    if (!m) return 0.01;
    if (/0\.001|0,001/.test(raw)) return 0.001;
    if (/0\.02|0,02/.test(raw)) return 0.02;
    if (/^DVC$|^DHG$|^DHI$|^DMM$|^MM$|^CMM$|VERNIER|CALIPER|CALLIPER|VENIRE|HEIGHT\s*GAU|HIEGHT|DIAL\s*GAU|MICROMETER|\bMIC\b|BORE\s*GAU|SURFACE\s*PLATE/.test(m)) {
      return 0.01;
    }
    if (/CMM|COORDINATE\s*MEASURING/.test(m)) return 0.001;
    return 0.01;
  }

  function firRoundToDecimals(value, decimals) {
    var n = Number(value);
    if (isNaN(n)) return null;
    var mul = Math.pow(10, decimals);
    return Math.round(n * mul) / mul;
  }

  /** Dimensional measured cells: at most 2 decimal places (avoids 6.4499999 float noise). */
  function firFormatTwoDecimalMeasured(value) {
    var n = firRoundToDecimals(value, 2);
    if (n == null || isNaN(n)) return String(value);
    if (Number.isInteger(n)) return String(n);
    return n.toFixed(2);
  }

  function firFormatLimitMeasured(value, resolutionStep) {
    var step = resolutionStep || 0.01;
    var mul = Math.round(1 / step);
    var snapped = Math.round(Number(value) * mul) / mul;
    return firFormatTwoDecimalMeasured(snapped);
  }

  function randomInRange(min, max, step) {
    if (max < min) { const t = min; min = max; max = t; }
    var v;
    if (min === max) {
      if (step === 0.5) v = Math.round(min * 2) / 2;
      else if (step === 0.1) v = Number(min.toFixed(1));
      else v = Number(min.toFixed(2));
    } else if (step === 0.5) {
      const steps = Math.round((max - min) / 0.5) + 1;
      const idx = Math.floor(Math.random() * steps);
      v = Math.round((min + idx * 0.5) * 2) / 2;
      v = Number(v.toFixed(1));
    } else if (step === 0.1) {
      const steps = Math.round((max - min) / 0.1) + 1;
      const idx = Math.floor(Math.random() * steps);
      v = Math.round((min + idx * 0.1) * 10) / 10;
      v = Number(v.toFixed(1));
    } else if (step && step > 0 && step < 1) {
      var mul = Math.round(1 / step);
      var nSteps = Math.max(1, Math.round((max - min) * mul) + 1);
      var pick = Math.floor(Math.random() * nSteps);
      v = Math.round((min + pick * step) * mul) / mul;
      v = firRoundToDecimals(v, 2);
    } else {
      v = min + Math.random() * (max - min);
      v = firRoundToDecimals(v, 2);
    }
    if (v < min) v = min;
    if (v > max) v = max;
    if (step === 0.1) v = Number(Number(v).toFixed(1));
    else if (step !== 0.5) v = firRoundToDecimals(v, 2);
    return v;
  }

  function isWithinSpec(value, min, max, precision) {
    const n = parseFloat(String(value).replace(/[^\d.-]/g, ""));
    if (isNaN(n)) return false;
    var p = precision != null ? precision : Math.max(firDecimalPlacesFromString(min), firDecimalPlacesFromString(max), 2);
    var nv = firRoundToDecimals(n, p);
    var nmin = firRoundToDecimals(min, p);
    var nmax = firRoundToDecimals(max, p);
    return nv >= nmin && nv <= nmax;
  }

  /** DFT / thickness in microns — parameter + spec + method (DFT METER). */
  function firIsDftStyleRow(param, spec, method) {
    var p = (param || "").toUpperCase();
    var s = (spec || "").toLowerCase();
    var m = String(method || "").trim().toUpperCase();
    if (p.indexOf("DFT") !== -1) return true;
    if (m === "DFT" || m === "DFT METER" || m.indexOf("DFT") === 0) return true;
    if (/\bmicron|\bmicrons\b|\bmic\b/.test(s)) return true;
    if (/\bum\b/.test(s) || s.indexOf("µ") !== -1) return true;
    return false;
  }

  function formatMeasuredValue(value, range) {
    if (!range) return String(value);
    if (range.isRadius) {
      // Radius rows should look like R6, R6.5, R5
      const num = Number(value);
      const text = Number.isInteger(num) ? String(num) : String(num).replace(/\.?0+$/, "");
      return `R${text}`;
    }
    if (range.isAngle) {
      // Angle rows should explicitly show degree symbol.
      const num = Number(value);
      const text = Number(num.toFixed(2)).toString();
      return `${text}\u00B0`;
    }
    if (range.oneDecimal) {
      return Number(value).toFixed(1);
    }
    if (range.limitFromZero && range.limitResolution) {
      return firFormatLimitMeasured(value, range.limitResolution);
    }
    return firFormatTwoDecimalMeasured(value);
  }

  /** Recompute Remarks from spec + filled measured cells (active sample columns only). */
  function firUpdateRowRemarksFromMeasurements(tr) {
    if (!tr || firIsNoCpiRow(tr)) return;
    if (firIsMilliporeRow(tr)) {
      var mCells = tr.querySelectorAll(":scope > td");
      if (mCells.length < 7) return;
      var specElM = mCells[2].querySelector("textarea") || mCells[2].querySelector("input");
      var methodElM = firQueryMethodInput(mCells[4]);
      var remarksElM = mCells[6].querySelector("input.remarks-value") || mCells[6].querySelector("input");
      var measuredElM = mCells[5].querySelector("input.actual-value") || mCells[5].querySelector("input");
      if (!specElM || !methodElM || !remarksElM || !measuredElM) return;
      var mp = firParseMilliporeSpec((specElM.value || "").trim());
      if (!mp) {
        remarksElM.value = "";
        updateStatusButtons();
        return;
      }
      var actualM = firParseMilliporeActual(measuredElM.value);
      var rawMp = String(measuredElM.value || "").trim();
      if (actualM == null || rawMp === "") {
        remarksElM.value = "";
      } else if (firMilliporePasses(actualM, mp.limit)) {
        measuredElM.value = firFormatMilliporeMessage(actualM, mp.unit);
        remarksElM.value = "OK";
      } else {
        if (/^Millipore\s+test\s+achieved/i.test(rawMp)) {
          measuredElM.value = firFormatMilliporeActualDisplay(actualM, mp.unit);
        }
        remarksElM.value = "Not OK";
      }
      updateStatusButtons();
      return;
    }
    var cells = tr.querySelectorAll(":scope > td");
    if (cells.length < 11) return;
    var specEl = cells[2].querySelector("textarea") || cells[2].querySelector("input");
    var methodEl = firQueryMethodInput(cells[4]);
    var remarksEl = cells[10].querySelector("input.remarks-value") || cells[10].querySelector("input");
    if (!specEl || !methodEl || !remarksEl) return;
    var methodRaw = (methodEl.value || "").trim();
    var paramEl = cells[1].querySelector("textarea") || cells[1].querySelector("input");
    var paramRaw = paramEl ? (paramEl.value || "").trim() : "";
    var spec = (specEl.value || "").trim();
    if (firRowUsesQualitativeMeasured(paramRaw, spec, methodRaw)) {
      firFillQualitativeMeasuredRow(tr);
      return;
    }
    /* Switching away from qualitative rows: measured cells may still contain "OK" — clear before numeric check */
    for (var cPre = 5; cPre <= 9; cPre++) {
      var tdPre = cells[cPre];
      if (!tdPre) continue;
      var inpPre = tdPre.querySelector("input.actual-value") || tdPre.querySelector('input[type="text"]');
      if (!inpPre || inpPre.disabled) continue;
      if ((inpPre.value || "").trim().toUpperCase() === "OK") inpPre.value = "";
    }
    var range = parseSpec(spec);
    if (!range) {
      remarksEl.value = "";
      updateStatusButtons();
      return;
    }
    var nActive = firGetMeasuredColumnCount();
    var min = range.min, max = range.max;
    var precision = range.precision != null ? range.precision : 2;
    var allOk = true;
    for (var ci = 5; ci < 5 + nActive && ci <= 9; ci++) {
      var td = cells[ci];
      if (!td) { allOk = false; break; }
      var inp = td.querySelector("input.actual-value") || td.querySelector('input[type="text"]');
      if (!inp || inp.disabled) continue;
      var raw = (inp.value || "").trim();
      if (raw === "") { allOk = false; break; }
      var parsedNum = parseFloat(String(raw).replace(/[^\d.-]/g, ""));
      if (!isNaN(parsedNum) && !/^R/i.test(raw) && raw.indexOf("\u00B0") === -1) {
        var fmt = formatMeasuredValue(parsedNum, range);
        if (fmt !== raw) {
          inp.value = fmt;
          raw = fmt;
        }
      }
      if (!isWithinSpec(raw, min, max, precision)) allOk = false;
    }
    remarksEl.value = allOk ? "OK" : "Not OK";
    updateStatusButtons();
  }

  /** Sl No | Parameter | Specification | Special char | Method | 5× actual | Remarks (11 cells) */
  function fillOneRow(tr) {
    if (firIsNoCpiRow(tr)) return;
    firSyncMilliporeRowLayout(tr);
    if (firIsMilliporeRow(tr)) {
      var mCells = tr.querySelectorAll(":scope > td");
      if (mCells.length < 7) return;
      var specElMp = mCells[2].querySelector("textarea") || mCells[2].querySelector("input");
      var methodElMp = firQueryMethodInput(mCells[4]);
      var remarksElMp = mCells[6].querySelector("input.remarks-value") || mCells[6].querySelector("input");
      var measuredElMp = mCells[5].querySelector("input.actual-value") || mCells[5].querySelector("input");
      if (!specElMp || !methodElMp || !remarksElMp || !measuredElMp) return;
      var resolvedMp = firResolveRowMeasuredContext(
        firRowTextFromCell(mCells[1]),
        (specElMp.value || "").trim(),
        (methodElMp.value || "").trim()
      );
      if (resolvedMp.mode !== "millipore") return;
      var sampleVal = firRandomMilliporeValue(resolvedMp.limit);
      measuredElMp.value = firFormatMilliporeMessage(sampleVal, resolvedMp.unit);
      remarksElMp.value = firMilliporePasses(sampleVal, resolvedMp.limit) ? "OK" : "Not OK";
      updateStatusButtons();
      return;
    }
    var cells = tr.querySelectorAll(":scope > td");
    if (cells.length < 11) return;
    var specEl = cells[2].querySelector("textarea") || cells[2].querySelector("input");
    var methodEl = firQueryMethodInput(cells[4]);
    var remarksEl = cells[10].querySelector("input.remarks-value") || cells[10].querySelector("input");
    if (!specEl || !methodEl || !remarksEl) return;
    var actualInputs = [];
    for (var ci = 5; ci <= 9; ci++) {
      var inp = cells[ci].querySelector("input.actual-value") || cells[ci].querySelector('input[type="text"]');
      if (!inp) return;
      actualInputs.push(inp);
    }
    var nActive = firGetMeasuredColumnCount();
    var spec = (specEl.value || "").trim();
    var paramEl = cells[1].querySelector("textarea") || cells[1].querySelector("input");
    var paramText = paramEl ? (paramEl.value || "").trim() : "";
    var methodText = (methodEl.value || "").trim();
    var resolved = firResolveRowMeasuredContext(paramText, spec, methodText);
    if (resolved.mode === "qualitative") {
      if (firIsMetricThreadSpecification(spec)) {
        methodEl.value = "TPG";
      }
      firFillQualitativeMeasuredRow(tr);
      return;
    }
    if (resolved.mode !== "numeric" || !resolved.range) {
      actualInputs.forEach(function(inp) { inp.value = ""; });
      remarksEl.value = "";
      updateStatusButtons();
      return;
    }
    var range = resolved.range;
    var min = range.min, max = range.max, step = range.step;
    var values = [];
    for (var i = 0; i < nActive; i++) values.push(randomInRange(min, max, step));
    var formatted = values.map(function(v) { return formatMeasuredValue(v, range); });
    actualInputs.forEach(function(inp, idx) {
      if (idx < nActive) inp.value = formatted[idx];
      else inp.value = "";
    });
    firUpdateRowRemarksFromMeasurements(tr);
  }

  function autoFillMeasuredValues() {
    firApplyMeasuredColumnAvailability();
    firSyncAllMilliporeRowLayouts();
    ["dimension-table", "coating-table"].forEach(function(tableId) {
      const table = document.getElementById(tableId);
      if (!table) return;
      table.querySelectorAll("tbody tr").forEach(function(tr) {
        fillOneRow(tr);
      });
    });
    var ccpTable = document.getElementById("ccp-table");
    if (ccpTable && !firSectionBIsNoCpiOnly()) {
      ccpTable.querySelectorAll("tbody tr").forEach(function(tr) {
        if (!tr.classList.contains("fir-no-cpi-row")) fillOneRow(tr);
      });
    }
    firApplyMeasuredColumnAvailability();
    firRefreshQualitativeMeasuredCellsInTables();
    const materialTable = document.getElementById("material-table");
    if (materialTable) {
      materialTable.querySelectorAll("tbody tr").forEach(tr => {
        const inputs = tr.querySelectorAll("input[type='text']");
        const remarksInput = inputs[inputs.length - 1];
        if (remarksInput && remarksInput.classList.contains("remarks-value")) remarksInput.value = "OK";
      });
    }
  }

  var autofillBtn = document.getElementById("autofillMeasuredBtn");
  if (autofillBtn) {
    autofillBtn.addEventListener("click", function() {
      autoFillMeasuredValues();
      updateStatusButtons();
    });
  }

  // --- Smart paste ---
  document.addEventListener("paste", e => {
    const active = document.activeElement;
    if (active && active.disabled) return;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text");
      const rows = text.trim().split(/\r?\n/);
      const rowEl = active.closest("tr");
      if (!rowEl) return;

      const allInputs = Array.from(rowEl.querySelectorAll("input[type='text'], textarea")).filter(
        (el) => !el.disabled
      );
      const currentIndex = allInputs.indexOf(active);

      let rIndex = 0;
      for (const rowData of rows) {
        const cells = rowData.split(/\t/);
        for (let c = 0; c < cells.length; c++) {
          const target = allInputs[currentIndex + c + rIndex * allInputs.length];
          if (target) target.value = cells[c].trim();
        }
        rIndex++;
      }
      const event = new Event("input", { bubbles: true });
      active.dispatchEvent(event);
      if (rowEl) firUpdateRowRemarksFromMeasurements(rowEl);
    }
  });

  /** html2pdf/html2canvas does not reliably apply CSS filter: grayscale — rasterize imgs to grey JPEGs before capture */
  function firGrayscaleImageForPdf(img) {
    return new Promise(function(resolve) {
      if (!img || !img.getAttribute("src")) {
        resolve();
        return;
      }
      if (img.dataset.firPdfOrigSrc) {
        resolve();
        return;
      }
      var finish = function() {
        resolve();
      };
      var apply = function() {
        try {
          var w = img.naturalWidth || img.width;
          var h = img.naturalHeight || img.height;
          if (!w || !h) {
            finish();
            return;
          }
          var maxEdge = typeof FIR_PDF_IMG_MAX_EDGE !== "undefined" ? FIR_PDF_IMG_MAX_EDGE : 100000;
          if (maxEdge > 0 && maxEdge < 100000 && (w > maxEdge || h > maxEdge)) {
            var shrink = Math.min(maxEdge / w, maxEdge / h);
            w = Math.max(1, Math.round(w * shrink));
            h = Math.max(1, Math.round(h * shrink));
          }
          var c = document.createElement("canvas");
          c.width = w;
          c.height = h;
          var ctx = c.getContext("2d");
          ctx.drawImage(img, 0, 0, w, h);
          var idata = ctx.getImageData(0, 0, w, h);
          var d = idata.data;
          for (var i = 0; i < d.length; i += 4) {
            var g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
            d[i] = d[i + 1] = d[i + 2] = g;
          }
          ctx.putImageData(idata, 0, 0);
          img.dataset.firPdfOrigSrc = img.src;
          img.src = c.toDataURL("image/jpeg", FIR_PDF_IMG_JPEG);
        } catch (e) {
          /* tainted canvas (cross-origin without CORS) — keep original */
        }
        finish();
      };
      if (img.complete && img.naturalWidth) {
        apply();
      } else {
        img.onload = function() {
          apply();
        };
        img.onerror = finish;
      }
    });
  }

  function firPrepareImagesForPdf(root) {
    var imgs = Array.prototype.slice.call(root.querySelectorAll("img"));
    return Promise.all(imgs.map(function(im) {
      return firGrayscaleImageForPdf(im);
    }));
  }

  function firRestoreImagesAfterPdf(root) {
    Array.prototype.forEach.call(root.querySelectorAll("img[data-fir-pdf-orig-src]"), function(img) {
      img.src = img.dataset.firPdfOrigSrc;
      img.removeAttribute("data-fir-pdf-orig-src");
    });
  }

  /** Dimension row count — used to decide single-page landscape PDF when < 10. */
  function firDimensionParameterCount() {
    if (FIR_SPEC_DATA.length > 0) return FIR_SPEC_DATA.length;
    if (noOfParamsParam && noOfParamsParam > 0) return noOfParamsParam;
    return totalRows;
  }

  function firShouldFitOneLandscapePage() {
    return firDimensionParameterCount() > 0 && firDimensionParameterCount() < 10;
  }

  /**
   * html2canvas clips textarea content even after autosize — swap to static divs for PDF capture.
   */
  function firPrepareTextareasForPdf(root) {
    root = root || document.getElementById("reportRoot");
    if (!root) return;
    firAutosizeAllTextareas(root);
    root.querySelectorAll("textarea").forEach(function(ta) {
      if (ta.dataset.firPdfHidden) return;
      var div = document.createElement("div");
      div.className = (ta.className || "") + " fir-pdf-text";
      if (ta.classList.contains("method-input")) div.classList.add("method-input");
      div.textContent = ta.value;
      div.setAttribute("data-fir-pdf-replaced", "1");
      ta.dataset.firPdfHidden = "1";
      ta.style.display = "none";
      ta.parentNode.insertBefore(div, ta.nextSibling);
    });
  }

  function firRestoreTextareasAfterPdf(root) {
    root = root || document.getElementById("reportRoot");
    if (!root) return;
    root.querySelectorAll("[data-fir-pdf-replaced]").forEach(function(div) {
      div.remove();
    });
    root.querySelectorAll("textarea[data-fir-pdf-hidden]").forEach(function(ta) {
      ta.style.display = "";
      ta.removeAttribute("data-fir-pdf-hidden");
    });
  }

  /** Shrink report uniformly (same X and Y) to fit one landscape A4 page when parameter count < 10. */
  function firApplyOnePagePdfScale(root) {
    root = root || document.getElementById("reportRoot");
    if (!root || !firShouldFitOneLandscapePage()) return;
    var container = root.querySelector(".report-container");
    if (!container) return;
    document.body.classList.add("fir-fit-one-page");

    var pxPerMm = 96 / 25.4;
    var maxH = 210 * pxPerMm - 4;
    var maxW = 270 * pxPerMm;
    var naturalH = container.offsetHeight || container.scrollHeight;
    var naturalW = container.offsetWidth || root.offsetWidth;
    if (!naturalH || !naturalW) return;

    var scale = Math.min(maxH / naturalH, maxW / naturalW, 1) * 0.985;
    if (scale >= 0.995) return;

    container.dataset.firPdfOrigTransform = container.style.transform || "";
    container.dataset.firPdfOrigMarginBottom = container.style.marginBottom || "";
    container.style.transform = "scale(" + scale + ")";
    container.style.transformOrigin = "top left";
    container.style.marginBottom = (-(naturalH * (1 - scale))) + "px";

    root.style.width = Math.ceil(naturalW * scale) + "px";
    root.style.height = Math.ceil(naturalH * scale) + "px";
    root.style.overflow = "hidden";
    root.style.margin = "0 auto";
    root.dataset.firPdfScale = String(scale);
  }

  function firRestoreOnePagePdfLayout(root) {
    root = root || document.getElementById("reportRoot");
    document.body.classList.remove("fir-fit-one-page");
    if (!root) return;
    var container = root.querySelector(".report-container");
    if (container) {
      container.style.transform = container.dataset.firPdfOrigTransform || "";
      container.style.transformOrigin = "";
      container.style.marginBottom = container.dataset.firPdfOrigMarginBottom || "";
      container.removeAttribute("data-fir-pdf-orig-transform");
      container.removeAttribute("data-fir-pdf-orig-margin-bottom");
    }
    root.style.width = "";
    root.style.height = "";
    root.style.overflow = "";
    root.style.margin = "";
    root.removeAttribute("data-fir-pdf-scale");
  }

  /** Compensate html2canvas scale when the report is uniformly shrunk so text stays sharp. */
  function firPdfHtml2canvasScale(root) {
    var fit = root && root.dataset.firPdfScale ? parseFloat(root.dataset.firPdfScale) : 1;
    if (!(fit > 0 && fit < 1)) return FIR_PDF_CANVAS_SCALE;
    return Math.min(3, FIR_PDF_CANVAS_SCALE / fit);
  }

  function firBuildPdfOptions(el, fileName) {
    var canvasScale = firPdfHtml2canvasScale(el);
    var jpegQuality = el && el.dataset.firPdfScale ? Math.min(0.88, FIR_PDF_JPEG_QUALITY + 0.12) : FIR_PDF_JPEG_QUALITY;
    return {
      margin: 0,
      filename: fileName,
      image: { type: "jpeg", quality: jpegQuality },
      html2canvas: {
        scale: canvasScale,
        useCORS: true,
        logging: false,
        scrollY: 0,
        scrollX: 0,
        width: el.offsetWidth || undefined,
        height: el.offsetHeight || undefined,
        windowWidth: el.offsetWidth || undefined,
        windowHeight: el.offsetHeight || undefined,
      },
      jsPDF: { unit: "mm", format: "a4", orientation: "landscape" },
      pagebreak: { mode: el && el.dataset.firPdfScale ? ["avoid-all"] : ["css"] },
    };
  }

  function firPrepareDomForPdfCapture(root) {
    root = root || document.getElementById("reportRoot");
    firPrepareTextareasForPdf(root);
    firApplyOnePagePdfScale(root);
    return new Promise(function(res) {
      requestAnimationFrame(function() {
        requestAnimationFrame(res);
      });
    });
  }

  function firRestoreDomAfterPdfCapture(root) {
    root = root || document.getElementById("reportRoot");
    firRestoreTextareasAfterPdf(root);
    firRestoreOnePagePdfLayout(root);
    firRestoreImagesAfterPdf(root);
  }

  /** Wait for Quali/custom fonts + logo/signature images before html2canvas capture */
  function firWaitForAssets(root) {
    root = root || document.getElementById("reportRoot");
    if (!root) return Promise.resolve();
    var fontWait =
      typeof document.fonts !== "undefined" && document.fonts.ready
        ? document.fonts.ready
        : Promise.resolve();
    return fontWait.then(function() {
      var imgs = Array.prototype.slice.call(root.querySelectorAll("img"));
      return Promise.all(
        imgs.map(function(img) {
          if (!img.getAttribute("src")) return Promise.resolve();
          if (img.complete && img.naturalWidth) {
            if (img.decode && typeof img.decode === "function") {
              return img.decode().catch(function() { return undefined; });
            }
            return Promise.resolve();
          }
          return new Promise(function(res) {
            img.onload = function() {
              if (img.decode && typeof img.decode === "function") {
                img.decode().catch(function() {}).finally(function() { res(); });
              } else {
                res();
              }
            };
            img.onerror = function() { res(); };
          });
        })
      );
    }).then(function() {
      firAutosizeAllTextareas(root);
      return new Promise(function(res) {
        requestAnimationFrame(function() {
          requestAnimationFrame(res);
        });
      });
    });
  }

  // --- PDF Download ---
  var downloadBtn = document.getElementById("downloadPDF");
  if (downloadBtn) {
    downloadBtn.addEventListener("click", function() {
    const btn = document.getElementById("downloadPDF");
    const autofillBtn = document.getElementById("autofillMeasuredBtn");
    btn.style.display = "none";
    if (autofillBtn) autofillBtn.style.display = "none";
    const el = document.getElementById('reportRoot') || document.body;

    document.body.classList.add('generating-pdf');
    const partInput = [...document.querySelectorAll('input[type="text"]')].find(i => i.closest('td')?.previousElementSibling?.textContent?.includes("PART"));
    const invoiceInput = [...document.querySelectorAll('input[type="text"]')].find(i => i.closest('td')?.previousElementSibling?.textContent?.includes("INVOICE"));
    const fileName = `${(invoiceInput?.value || 'Invoice').replace(/\W+/g,'_')}_${(partInput?.value || 'Part').replace(/\W+/g,'_')}_FIR.pdf`;

    function restorePdfUi() {
      firRestoreDomAfterPdfCapture(el);
      document.body.classList.remove('generating-pdf');
      btn.style.display = "block";
      if (autofillBtn) autofillBtn.style.display = "block";
    }

    firWaitForAssets(el).then(function() {
      return firPrepareImagesForPdf(el);
    }).then(function() {
      return firPrepareDomForPdfCapture(el);
    }).then(function() {
      return html2pdf().set(firBuildPdfOptions(el, fileName)).from(el).save();
    }).then(restorePdfUi).catch(function() {
      restorePdfUi();
    });
  });
  }

  /** Batch tools on parent page (e.g. SaaS inspection results): same-origin iframes only */
  function firGeneratePdfBlob() {
    return new Promise(function(resolve, reject) {
      var waitStart = Date.now();
      function waitForHtml2pdf(thenFn) {
        if (typeof html2pdf !== "undefined") {
          thenFn();
          return;
        }
        if (Date.now() - waitStart > 20000) {
          reject(new Error("html2pdf not loaded"));
          return;
        }
        setTimeout(function () { waitForHtml2pdf(thenFn); }, 100);
      }
      waitForHtml2pdf(function () {
      var btn = document.getElementById("downloadPDF");
      var autofillBtnEl = document.getElementById("autofillMeasuredBtn");
      if (btn) btn.style.display = "none";
      if (autofillBtnEl) autofillBtnEl.style.display = "none";
      var el = document.getElementById('reportRoot') || document.body;
      document.body.classList.add('generating-pdf');
      var textInputs = Array.prototype.slice.call(document.querySelectorAll('input[type="text"]'));
      var partInput = textInputs.find(function(i) {
        var td = i.closest('td');
        return td && td.previousElementSibling && td.previousElementSibling.textContent && td.previousElementSibling.textContent.indexOf("PART") !== -1;
      });
      var invoiceInput = textInputs.find(function(i) {
        var td = i.closest('td');
        return td && td.previousElementSibling && td.previousElementSibling.textContent && td.previousElementSibling.textContent.indexOf("INVOICE") !== -1;
      });
      var fileName = ((invoiceInput && invoiceInput.value) || 'Invoice').replace(/\W+/g,'_') + '_' + ((partInput && partInput.value) || 'Part').replace(/\W+/g,'_') + '_FIR.pdf';

      function restoreUi() {
        firRestoreDomAfterPdfCapture(el);
        document.body.classList.remove('generating-pdf');
        if (btn) btn.style.display = "block";
        if (autofillBtnEl) autofillBtnEl.style.display = "block";
      }

      firWaitForAssets(el).then(function() {
        return firPrepareImagesForPdf(el);
      }).then(function() {
        return firPrepareDomForPdfCapture(el);
      }).then(function() {
        var worker = html2pdf().set(firBuildPdfOptions(el, fileName)).from(el);

        var out = null;
        if (typeof worker.outputPdf === 'function') {
          out = worker.outputPdf('blob');
        } else if (typeof worker.output === 'function') {
          out = worker.output('blob');
        }
        if (out && typeof out.then === 'function') {
          out.then(function(blob) {
            restoreUi();
            var n = blob && blob.size ? blob.size : 0;
            var warn = "";
            if (n > 200 * 1024) {
              warn = "over_200kb";
            } else if (n > 0 && n < 100 * 1024) {
              warn = "under_100kb";
            }
            resolve({
              blob: blob,
              filename: fileName,
              byteSize: n,
              sizeWarning: warn || undefined
            });
          }).catch(function(err) {
            restoreUi();
            reject(err);
          });
        } else {
          restoreUi();
          reject(new Error('html2pdf blob output not available in this build'));
        }
      }).catch(function(err) {
        restoreUi();
        reject(err);
      });
      });
    });
  }

  window.FIR_PREVIEW_API = {
    get ready() {
      try {
        return !!document.getElementById('dimension-table');
      } catch (e) {
        return false;
      }
    },
    waitForAssets: function() {
      return firWaitForAssets(document.getElementById('reportRoot'));
    },
    autoFillMeasuredValues: function() {
      autoFillMeasuredValues();
      updateStatusButtons();
    },
    generatePdfBlob: firGeneratePdfBlob
  };

  /* Parent page (Amplify) is cross-origin from this document (Railway): use postMessage for batch tools. */
  (function setupParentBridge() {
    var frameIndex = parseInt(firQueryParam("previewFrameIndex") || "-1", 10);
    if (isNaN(frameIndex)) frameIndex = -1;
    if (frameIndex < 0 || window.parent === window) return;

    var readySent = false;
    var readyIv = setInterval(function () {
      if (readySent) {
        clearInterval(readyIv);
        return;
      }
      try {
        if (window.FIR_PREVIEW_API && window.FIR_PREVIEW_API.ready) {
          readySent = true;
          clearInterval(readyIv);
          window.parent.postMessage(
            { source: "fir-saas-fir-preview", type: "ready", frameIndex: frameIndex },
            "*"
          );
        }
      } catch (e) {}
    }, 200);
    setTimeout(function () {
      clearInterval(readyIv);
    }, 45000);

    window.addEventListener("message", function (ev) {
      var d = ev.data;
      if (!d || d.source !== "fir-saas-fir-preview-parent") return;
      if (d.type === "autoFill" && window.FIR_PREVIEW_API) {
        window.FIR_PREVIEW_API.autoFillMeasuredValues();
        return;
      }
      if (d.type === "generatePdf" && window.FIR_PREVIEW_API && window.FIR_PREVIEW_API.generatePdfBlob) {
        var reqId = d.requestId;
        var reply = ev.source;
        var finishErr = function (err) {
          if (reply)
            reply.postMessage(
              {
                source: "fir-saas-fir-preview",
                type: "pdfBlobResult",
                frameIndex: frameIndex,
                requestId: reqId,
                ok: false,
                error: String((err && err.message) || err),
              },
              "*"
            );
        };
        var run = function () {
          window.FIR_PREVIEW_API
            .generatePdfBlob()
            .then(function (result) {
              if (reply)
                reply.postMessage(
                  {
                    source: "fir-saas-fir-preview",
                    type: "pdfBlobResult",
                    frameIndex: frameIndex,
                    requestId: reqId,
                    ok: true,
                    filename: result.filename,
                    byteSize: result.byteSize,
                    sizeWarning: result.sizeWarning,
                    blob: result.blob,
                  },
                  "*"
                );
            })
            .catch(finishErr);
        };
        run();
      }
    });
  })();
})();
