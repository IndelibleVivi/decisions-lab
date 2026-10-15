// Progressive enhancement for the catalog category selector on the homepage.
//
// Contract (DOM emitted by the page template; this file never invents facts):
//   #project-atlas                       container for the selector
//   buttons  [data-atlas-group="<ID>"]   one control per group (type=button)
//   panels   [data-atlas-panel="<ID>"]   real links into docs/projects.html
//   #atlas-status                        role=status live region for the label
//   .atlas-controls                      inside #project-atlas, hidden at first
//
// Static fallback: the template renders only the first panel visible at first;
// with JavaScript disabled the remaining categories are still reachable through
// the separate project-directory link, not through hidden in-page markup. This
// script only reveals the controls after it has proved the DOM is coherent —
// every button has a matching panel and vice versa, each group appears exactly
// once — and leaves them hidden if anything is missing or duplicated. Selecting
// a control toggles visibility and aria-pressed, then announces the selected
// label. Groups are addressed by stable ID, never by position.
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module && module.exports) module.exports = api; // Node tests
  if (typeof document === 'undefined') return; // browser-only DOM wiring below
  api.mount(document);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function groupAttr(element, attribute) {
    var value = element.getAttribute(attribute);
    return value == null ? '' : value;
  }

  // Collect buttons and panels, dropping any element missing a non-empty group
  // id. Returns null (caller keeps the fallback) when the pairing is not exactly
  // one-to-one, so malformed markup can never leave a group without a control
  // or a control without a panel.
  function collect(root) {
    var buttons = [], panels = [];
    var buttonNodes = root.querySelectorAll('[data-atlas-group]');
    var panelNodes = root.querySelectorAll('[data-atlas-panel]');
    for (var i = 0; i < buttonNodes.length; i++) {
      var group = groupAttr(buttonNodes[i], 'data-atlas-group');
      if (!group) return null;
      buttons.push({ group: group, node: buttonNodes[i] });
    }
    for (var j = 0; j < panelNodes.length; j++) {
      var panelGroup = groupAttr(panelNodes[j], 'data-atlas-panel');
      if (!panelGroup) return null;
      panels.push({ group: panelGroup, node: panelNodes[j] });
    }
    if (!buttons.length || buttons.length !== panels.length) return null;

    var seen = {};
    for (var k = 0; k < buttons.length; k++) {
      if (seen[buttons[k].group]) return null; // duplicate button id
      seen[buttons[k].group] = 'button';
    }
    for (var m = 0; m < panels.length; m++) {
      if (!seen[panels[m].group]) return null; // panel without a control
      if (seen[panels[m].group] === 'panel') return null; // duplicate panel id
      seen[panels[m].group] = 'panel';
    }
    // Counts matched and no duplicates, so every control has exactly one panel.
    return { buttons: buttons, panels: panels };
  }

  function mount(doc) {
    var root = doc.querySelector('#project-atlas');
    if (!root) return null;

    var controls = root.querySelector('.atlas-controls');
    var status = doc.getElementById('atlas-status');
    var pairs = collect(root);
    if (!pairs) return null; // leave the static fallback and hidden controls intact
    if (!controls) return null; // no reveal target: keep static panels untouched

    var buttons = pairs.buttons, panels = pairs.panels;
    // The statically visible panel owns the initial selection so enabling
    // JavaScript does not contradict the no-JS fallback. Group ids, not
    // button order, decide which control is pressed.
    var current = panels[0].group;

    function nodeFor(list, group) {
      for (var i = 0; i < list.length; i++) if (list[i].group === group) return list[i].node;
      return null;
    }

    function labelFor(group) {
      var node = nodeFor(buttons, group);
      var label = node && node.getAttribute('data-label');
      return label == null ? '' : label;
    }

    function render(group) {
      current = group;
      for (var i = 0; i < panels.length; i++) panels[i].node.hidden = panels[i].group !== group;
      for (var j = 0; j < buttons.length; j++) {
        buttons[j].node.setAttribute('aria-pressed', String(buttons[j].group === group));
      }
      if (status) status.textContent = labelFor(group);
    }

    function select(group) {
      if (!nodeFor(panels, group)) return null; // unknown id: never hide every panel
      if (group === current) return null; // idempotent re-selection
      render(group);
      return group;
    }

    for (var i = 0; i < buttons.length; i++) {
      (function (group) {
        nodeFor(buttons, group).addEventListener('click', function () { select(group); });
      })(buttons[i].group);
    }

    render(current);
    if (controls) controls.hidden = false;

    return { select: select, current: function () { return current; } };
  }

  return { mount: mount, collect: collect };
});
