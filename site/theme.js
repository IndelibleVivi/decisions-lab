// Local appearance preference only. No network or analytics.
(function () {
  'use strict';
  const system = matchMedia('(prefers-color-scheme: dark)');
  let chosen = null;
  try { chosen = localStorage.getItem('decisions-theme'); } catch (_) { /* storage may be disabled */ }
  if (!['light', 'dark'].includes(chosen)) chosen = null;
  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    const button = document.querySelector('#theme-toggle');
    if (button) {
      button.hidden = false;
      button.setAttribute('aria-label', theme === 'dark' ? '切换到日间模式' : '切换到夜间模式');
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      button.querySelector('span').textContent = theme === 'dark' ? 'DAY' : 'NIGHT';
    }
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#111d21' : '#f6f2e9';
    document.dispatchEvent(new Event('themechange'));
  }
  apply(chosen || (system.matches ? 'dark' : 'light'));
  document.addEventListener('DOMContentLoaded', () => {
    apply(document.documentElement.dataset.theme);
    document.querySelector('#theme-toggle').addEventListener('click', () => {
      chosen = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('decisions-theme', chosen); } catch (_) { /* still works for this page */ }
      apply(chosen);
    });
  });
  system.addEventListener('change', () => { if (!chosen) apply(system.matches ? 'dark' : 'light'); });
})();
