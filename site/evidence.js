// Historical pixel evidence explorer (progressive enhancement, no dependencies).
//
// Contract (emitted by the page template; this file never invents facts):
//   <script type="application/json" id="evidence-data">
//     [{id,label,total,correct,highTotal,highErrors}, ...]
//   </script>
//   #evidence-grid      SVG rect grid, viewBox="0 0 400 400", role="img"
//   #evidence-correct   #evidence-total   #evidence-accuracy   #evidence-errors
//   #evidence-summary   role=status
//   .evidence-controls  panel, initially hidden, revealed once JS runs
//   buttons [data-evidence-task="<id>"] and [data-evidence-scope="all"|"high"]
//   Initial selection: first task, scope "all".
//
// Every cell is one original decision, grouped by aggregate outcome — never by
// a claimed raw sample identity or order. High scope leaves the low cells in
// place at reduced opacity (CSS owns the look); the numbers then use only the
// high subset. A narrow pure partition function is shared with the count math
// and exported (guarded) for CommonJS tests.
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module && module.exports) module.exports = api; // Node tests
  if (typeof document === 'undefined') return; // browser-only DOM wiring below
  api.mount(document);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var SIZE = 400;        // SVG viewBox is 400x400
  var COLS = 20;         // 20 columns for a 400-case subset
  var CELL = 14;         // square side
  var PITCH = 18;        // centre-to-centre spacing

  function isCount(value) {
    return typeof value === 'number' && isFinite(value) && Math.floor(value) === value && value >= 0;
  }

  // Validate one aggregate record and split it into the four outcome groups.
  // Returns {ok:false, reason} instead of throwing so bad input can never
  // produce a misleading picture; the template's fallback table stays readable.
  function partition(record) {
    if (!record || typeof record !== 'object') return { ok: false, reason: 'not-an-object' };
    var total = record.total, correct = record.correct,
        highTotal = record.highTotal, highErrors = record.highErrors;
    var fields = ['total', 'correct', 'highTotal', 'highErrors'];
    for (var i = 0; i < fields.length; i++) {
      if (!isCount(record[fields[i]])) return { ok: false, reason: 'bad-' + fields[i] };
    }
    if (highTotal > total) return { ok: false, reason: 'high-total-exceeds-total' };
    if (correct > total) return { ok: false, reason: 'correct-exceeds-total' };
    if (highErrors > highTotal) return { ok: false, reason: 'high-errors-exceed-high-total' };
    var highCorrect = highTotal - highErrors;
    if (highCorrect > correct) return { ok: false, reason: 'high-correct-exceeds-correct' };
    var highWrong = highErrors;
    var lowCorrect = correct - highCorrect;
    var lowWrong = total - highTotal - lowCorrect;
    if (lowWrong < 0) return { ok: false, reason: 'high-errors-exceed-all-errors' };
    return {
      ok: true,
      total: total,
      correct: correct,
      highTotal: highTotal,
      highErrors: highErrors,
      highCorrect: highCorrect,
      highWrong: highWrong,
      lowCorrect: lowCorrect,
      lowWrong: lowWrong
    };
  }

  // Build the ordered cell list. Order is deterministic: high correct, high
  // wrong, low correct, low wrong. Grouping is by aggregate outcome, so the
  // arrangement carries no raw sample identity or original order.
  function cellsFor(parts) {
    var cells = [];
    function push(count, isError, isHigh) {
      for (var i = 0; i < count; i++) cells.push({ isError: isError, isHigh: isHigh });
    }
    push(parts.highCorrect, false, true);
    push(parts.highWrong, true, true);
    push(parts.lowCorrect, false, false);
    push(parts.lowWrong, true, false);
    return cells;
  }

  // Metrics for the chosen scope. "high" uses only highTotal; "all" uses total.
  function metrics(parts, scope) {
    if (scope === 'high') {
      return {
        correct: parts.highCorrect,
        total: parts.highTotal,
        errors: parts.highWrong,
        accuracy: parts.highTotal ? (100 * parts.highCorrect) / parts.highTotal : 0
      };
    }
    return {
      correct: parts.correct,
      total: parts.total,
      errors: parts.total - parts.correct,
      accuracy: parts.total ? (100 * parts.correct) / parts.total : 0
    };
  }

  function formatAccuracy(value) {
    return (Math.round(value * 10) / 10).toFixed(1) + '%';
  }

  var SVG_NS = 'http://www.w3.org/2000/svg';

  function mount(doc) {
    var dataNode = doc.querySelector('#evidence-data');
    var grid = doc.querySelector('#evidence-grid');
    // Both nodes must exist together, or there is nothing to enhance.
    if (!dataNode || !grid) return;

    var outCorrect = doc.querySelector('#evidence-correct');
    var outTotal = doc.querySelector('#evidence-total');
    var outAccuracy = doc.querySelector('#evidence-accuracy');
    var outErrors = doc.querySelector('#evidence-errors');
    var summary = doc.querySelector('#evidence-summary');
    var controls = doc.querySelector('.evidence-controls');
    if (!outCorrect || !outTotal || !outAccuracy || !outErrors || !summary) return;

    var records;
    try {
      var parsed = JSON.parse(dataNode.textContent);
      if (!Array.isArray(parsed) || parsed.length === 0) return;
      records = parsed;
      for (var i = 0; i < records.length; i++) {
        var raw = records[i];
        var check = partition(raw);
        if (!check.ok) return; // contradictory/missing data: leave fallback readable
        // Keep the authored identity/label alongside the derived group counts.
        check.id = raw && raw.id;
        check.label = raw && raw.label;
        records[i] = check;
      }
    } catch (err) {
      return; // malformed JSON: no uncaught error, fallback stays readable
    }

    var taskButtons = Array.prototype.slice.call(doc.querySelectorAll('[data-evidence-task]'));
    var scopeButtons = Array.prototype.slice.call(doc.querySelectorAll('[data-evidence-scope]'));
    var current = 0;
    var scope = 'all';
    var view = doc.defaultView;
    var reduced = view && view.matchMedia ? view.matchMedia('(prefers-reduced-motion: reduce)') : null;
    var animations = [], gridVisible = !view || !view.IntersectionObserver;
    var pixelPause = doc.querySelector('#pixel-pause');
    function cancelMotion() { animations.forEach(function (a) { a.cancel(); }); animations = []; }
    function animateCells() {
      cancelMotion();
      if (!gridVisible || doc.hidden || (reduced && reduced.matches) || (pixelPause && pixelPause.getAttribute('aria-pressed') === 'true')) return;
      var cells = grid.querySelectorAll('.evidence-cell');
      for (var i = 0; i < cells.length; i++) {
        if (!cells[i].animate) continue;
        animations.push(cells[i].animate([
          { transform: 'translateY(7px) scale(.35)' }, { transform: 'translateY(0) scale(1)' }
        ], { duration: 260, delay: (i % COLS) * 9 + Math.floor(i / COLS) * 7, easing: 'steps(5, end)' }));
      }
    }
    if (reduced) reduced.addEventListener('change', function () { if (reduced.matches) cancelMotion(); });
    if (doc.addEventListener) doc.addEventListener('visibilitychange', function () { if (doc.hidden) cancelMotion(); });
    if (pixelPause) pixelPause.addEventListener('click', cancelMotion);
    if (view && view.IntersectionObserver) new view.IntersectionObserver(function (entries) {
      gridVisible = entries[entries.length - 1].isIntersecting;
      if (!gridVisible) cancelMotion();
    }).observe(grid);


    function labelFor(index) {
      var label = records[index].label;
      return typeof label === 'string' && label ? label : records[index].id;
    }

    function buildCells(parts) {
      cancelMotion();
      grid.textContent = '';
      var cells = cellsFor(parts);
      var originX = (SIZE - ((COLS - 1) * PITCH + CELL)) / 2;
      var originY = (SIZE - ((Math.ceil(cells.length / COLS) - 1) * PITCH + CELL)) / 2;
      for (var n = 0; n < cells.length; n++) {
        var index = cells[n];
        var rect = doc.createElementNS(SVG_NS, 'rect');
        rect.setAttribute('x', String(originX + (n % COLS) * PITCH));
        rect.setAttribute('y', String(originY + Math.floor(n / COLS) * PITCH));
        rect.setAttribute('width', String(CELL));
        rect.setAttribute('height', String(CELL));
        rect.setAttribute('class',
          'evidence-cell ' + (index.isError ? 'is-error' : 'is-correct') +
          (index.isHigh ? '' : ' is-muted'));
        grid.appendChild(rect);
      }
    }

    // Scope never rebuilds cells; it only toggles the muted class, so rapid
    // task/scope switching always converges to a consistent final state.
    function syncScope() {
      var cells = grid.querySelectorAll('.evidence-cell');
      var parts = records[current];
      var highCount = parts.highCorrect + parts.highWrong;
      for (var n = 0; n < cells.length; n++) {
        var isHigh = n < highCount; // cells are ordered high-first
        var muted = scope === 'high' && !isHigh;
        if (muted) cells[n].classList.add('is-muted');
        else cells[n].classList.remove('is-muted');
      }
    }

    function paint() {
      var parts = records[current];
      var data = metrics(parts, scope);

      outCorrect.textContent = String(data.correct);
      outTotal.textContent = String(data.total);
      outAccuracy.textContent = formatAccuracy(data.accuracy);
      outErrors.textContent = String(data.errors);

      var scopeText = scope === 'high'
        ? '高置信度子集（maxP ≥ 0.9）：' + data.total + ' 项'
        : '全部记录：' + data.total + ' 项';
      summary.textContent =
        '历史任务「' + labelFor(current) + '」，' + scopeText +
        '，判断正确 ' + data.correct + ' / ' + data.total +
        '，准确率 ' + formatAccuracy(data.accuracy) +
        '，错误 ' + data.errors +
        '。这是历史公开预测的复算，不是当前模型排名。';

      grid.setAttribute('aria-label',
        '历史任务「' + labelFor(current) + '」' + scopeText +
        '按汇总数量排布：正确 ' + data.correct + ' 格，错误 ' + data.errors +
        ' 格，共 ' + data.total + ' 格。');
    }

    function selectTask(index) {
      current = index;
      buildCells(records[current]);
      syncScope();
      taskButtons.forEach(function (button) {
        button.setAttribute('aria-pressed', String(button.getAttribute('data-evidence-task') === records[index].id));
      });
      paint();
      animateCells();
    }

    function selectScope(next) {
      scope = next;
      scopeButtons.forEach(function (button) {
        button.setAttribute('aria-pressed', String(button.getAttribute('data-evidence-scope') === next));
      });
      syncScope();
      paint();
      animateCells();
    }

    taskButtons.forEach(function (button) {
      var index = records.findIndex(function (record) { return record.id === button.getAttribute('data-evidence-task'); });
      if (index >= 0) button.addEventListener('click', function () { selectTask(index); });
    });
    scopeButtons.forEach(function (button) {
      button.addEventListener('click', function () {
        selectScope(button.getAttribute('data-evidence-scope'));
      });
    });

    if (controls) controls.hidden = false;
    selectScope('all');
    selectTask(0);
  }

  return {
    partition: partition,
    cellsFor: cellsFor,
    metrics: metrics,
    formatAccuracy: formatAccuracy,
    mount: mount,
    CELL: CELL,
    PITCH: PITCH,
    COLS: COLS,
    SIZE: SIZE
  };
});
