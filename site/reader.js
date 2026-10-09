// Progressive enhancement for reader pages: copy buttons, TOC scroll-spy,
// and optional reading progress. No network, no storage, no framework.
// Everything here is additive: with JavaScript disabled the page is fully readable.
(function () {
  'use strict';

  /* ---------------------------------------------------------------- copy */
  // Add a copy button to every article <pre> (including ones that wrap <code>).
  // The original code node is never replaced; we only add sibling UI.
  function codeTextOf(pre) {
    var code = pre.querySelector('code');
    return (code || pre).textContent;
  }

  function fallbackCopy(text, onDone) {
    // No execCommand and no silent failure: report that the user should
    // select the code manually, which stays possible because we never
    // replace or hide the code node.
    void text;
    onDone(false);
  }

  function attachCopyButtons() {
    var blocks = document.querySelectorAll('article pre');
    if (!blocks.length) return;

    blocks.forEach(function (pre) {
      if (pre.querySelector('.copy-code')) return; // idempotent

      var originalText = codeTextOf(pre);
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'copy-code';
      button.textContent = '复制';
      button.setAttribute('aria-label', '复制这段代码');

      var statusEl = document.createElement('span');
      statusEl.className = 'copy-code-status';
      statusEl.setAttribute('role', 'status');
      statusEl.setAttribute('aria-live', 'polite');

      var timer = null;
      var say = function (msg) {
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
        statusEl.textContent = msg;
        if (msg) {
          timer = setTimeout(function () {
            statusEl.textContent = '';
          }, 2000);
        }
      };

      button.addEventListener('click', function () {
        var text = originalText;
        var done = function (ok) {
          if (ok) {
            button.textContent = '已复制';
            say('已复制');
            setTimeout(function () {
              button.textContent = '复制';
            }, 2000);
          } else {
            say('请选择代码复制');
          }
        };

        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
              done(true);
            }, function () {
              fallbackCopy(text, done);
            });
          } else {
            fallbackCopy(text, done);
          }
        } catch (e) {
          fallbackCopy(text, done);
        }
      });

      // Insert UI before the code block without disturbing its text content.
      pre.insertBefore(button, pre.firstChild);
      pre.insertBefore(statusEl, button.nextSibling);
    });
  }

  /* ----------------------------------------------------------- scroll spy */
  // Highlight the TOC link whose article h2 section currently owns the viewport.
  // We never call scrollIntoView; movement stays user-driven.
  function initToc() {
    var tocLinks = Array.prototype.slice.call(
      document.querySelectorAll('.toc a[href^="#"]')
    );
    var progressTargets = Array.prototype.slice.call(
      document.querySelectorAll('.reading-progress')
    );
    if (!tocLinks.length && !progressTargets.length) return;

    var pairs = tocLinks
      .map(function (link) {
        var id = decodeURIComponent(link.getAttribute('href').slice(1));
        var heading = document.getElementById(id);
        return heading ? { link: link, heading: heading } : null;
      })
      .filter(Boolean);

    var headings = Array.from(new Set(pairs.map(function (pair) { return pair.heading; })));
    var ticking = false;
    var lastActive = null;

    function currentHeadingIndex() {
      // The active section is the last heading at or above the reading line.
      // Both desktop and mobile anchors land below the sticky header (95/126px).
      var line = window.scrollY + 140;
      var index = -1;
      for (var i = 0; i < headings.length; i++) {
        var top = headings[i].getBoundingClientRect().top + window.scrollY;
        if (top <= line) index = i;
      }
      // At the very bottom always activate the final section.
      var doc = document.documentElement;
      var atBottom =
        window.innerHeight + window.scrollY >= doc.scrollHeight - 2;
      if (atBottom && headings.length) index = headings.length - 1;
      return index;
    }

    function updateActive() {
      if (!pairs.length) return;
      var index = currentHeadingIndex();
      if (index === lastActive) return; // quiet no-op when nothing changed
      lastActive = index;
      pairs.forEach(function (pair) {
        if (pair.heading === headings[index]) {
          pair.link.setAttribute('aria-current', 'location');
        } else {
          pair.link.removeAttribute('aria-current');
        }
      });
    }

    function updateProgress() {
      if (!progressTargets.length) return;
      var doc = document.documentElement;
      var total = doc.scrollHeight - window.innerHeight;
      var value = total > 0 ? window.scrollY / total : 0;
      if (value < 0) value = 0;
      if (value > 1) value = 1;
      progressTargets.forEach(function (el) {
        el.style.setProperty('--progress', String(value));
      });
    }

    function apply() {
      ticking = false;
      updateActive();
      updateProgress();
    }

    function onScroll() {
      if (ticking) return;
      ticking = true;
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(apply);
      } else {
        apply();
      }
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    apply();

  }

  /* ------------------------------------------------- mobile TOC details */
  // The template owns the native <details>/<summary>; when a link inside it is
  // clicked, close the disclosure once navigation has started.
  function initTocDetails() {
    var items = document.querySelectorAll('details.toc-details');
    items.forEach(function (item) {
      item.querySelectorAll('a[href^="#"]').forEach(function (link) {
        link.addEventListener('click', function () {
          item.open = false;
        });
      });
    });
  }

  attachCopyButtons();
  initTocDetails();
  initToc();
})();
