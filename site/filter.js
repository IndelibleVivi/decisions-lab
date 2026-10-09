// Progressive enhancement: search the single 21-project table set on the
// project map. Original evidence (group headings, boundary notes, links) stays
// fully readable when this file is disabled or the query matches nothing.
//
// Contract:
//   #project-filter  -> the search <input>; its presence gates everything.
//   #filter-result   -> role=status text target.
//   .filter          -> the search panel, revealed once JS is active.
//   #filter-clear    -> optional clear button; enabled only with a query.
//   .table-wrap      -> per-table wrapper (added by the template); hidden only
//                       when the query has no matching row in that table.
(function () {
  'use strict';

  var input = document.querySelector('#project-filter');
  if (!input) return; // Ordinary tables are never treated as project tables.

  var panel = document.querySelector('.filter');
  var status = document.querySelector('#filter-result');
  var clear = document.querySelector('#filter-clear');
  var matches = document.querySelector('#filter-matches');
  var tableWraps = Array.prototype.slice.call(
    document.querySelectorAll('article .table-wrap')
  );

  var groups = tableWraps.map(function (wrap) {
    return {
      wrap: wrap,
      rows: Array.prototype.slice.call(wrap.querySelectorAll('tbody tr'))
    };
  });

  var rowNumber = 0;
  groups.forEach(function (group) {
    group.rows.forEach(function (row) {
      row.id = 'project-row-' + (++rowNumber);
      row.setAttribute('tabindex', '-1');
    });
  });

  if (panel) panel.hidden = false;

  function totalCount() {
    var total = 0;
    groups.forEach(function (group) {
      total += group.rows.length;
    });
    return total;
  }

  function setStatus(text) {
    if (status) status.textContent = text;
  }

  function update() {
    var query = input.value.trim().toLocaleLowerCase();
    var matched = 0;
    if (matches) {
      matches.textContent = '';
      matches.hidden = true;
    }

    groups.forEach(function (group) {
      var groupMatches = 0;
      group.rows.forEach(function (row) {
        var hit =
          query === '' ||
          row.textContent.toLocaleLowerCase().indexOf(query) !== -1;
        row.hidden = !hit;
        if (hit) {
          groupMatches++;
          matched++;
          if (query && matches) {
            var link = document.createElement('a');
            link.setAttribute('href', '#' + row.id);
            link.textContent = row.querySelector('td').textContent + ' ↓';
            matches.appendChild(link);
            matches.hidden = false;
          }
        }
      });
      // Hide only the table wrapper with no matches; its group heading and the
      // boundary text below it stay visible.
      group.wrap.hidden = query !== '' && groupMatches === 0;
    });

    if (clear) clear.disabled = query === '';
    if (panel) panel.dataset.active = query === '' ? '' : 'active';

    if (query === '') {
      setStatus(
        '显示全部 ' + totalCount() + ' 个项目。下方的局限与追踪线索始终保留。'
      );
    } else if (matched === 0) {
      setStatus(
        '检索未命中任何项目。下方的分组标题、局限说明与追踪线索仍然完整可读；' +
        '搜索只覆盖项目表格，不会隐藏证据或来源。'
      );
    } else {
      setStatus(
        '显示 ' + matched + ' / ' + totalCount() + ' 个项目。无匹配的分组表格收起，' +
        '下方的局限与追踪线索始终保留。'
      );
    }
  }

  input.addEventListener('input', update);
  input.addEventListener('search', update); // native search clear affordance

  if (clear) {
    clear.addEventListener('click', function () {
      input.value = '';
      update();
      input.focus();
    });
  }

  update();
})();
