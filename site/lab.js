// A local view of three original synthetic cases. This never runs a model.
(() => {
  const data = document.querySelector('#sample-data');
  if (!data) return;
  const cases = JSON.parse(data.textContent);
  const selector = document.querySelector('#sample-case');
  const choices = [...document.querySelectorAll('[data-action]')];
  const feedback = document.querySelector('#sample-feedback');
  const documentText = document.querySelector('#sample-document');
  const claimText = document.querySelector('#sample-claim');
  const panel = document.querySelector('.specimen');
  const media = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
  const pause = document.querySelector('#pixel-pause');
  let animation = null, visible = typeof IntersectionObserver !== 'function';
  function motionAllowed() {
    return visible && !document.hidden && !(media && media.matches)
      && !(pause && pause.getAttribute('aria-pressed') === 'true');
  }
  function cancelMotion() {
    const current = animation; animation = null;
    if (current) current.cancel();
  }
  function syncMotion() { if (!motionAllowed()) cancelMotion(); }
  if (media) media.addEventListener('change', syncMotion);
  document.addEventListener('visibilitychange', syncMotion);
  document.addEventListener('pixelmotionchange', syncMotion);
  if (panel && typeof IntersectionObserver === 'function') new IntersectionObserver(entries => {
    visible = entries[entries.length - 1].isIntersecting;
    syncMotion();
  }).observe(panel);
  // Treat authored input as text, with only paired inline-code markers recognized.
  function renderText(target, text) {
    const parts = text.split(/(`[^`]+`)/g);
    target.replaceChildren(...parts.map(part => {
      if (part.startsWith('`') && part.endsWith('`')) {
        const code = document.createElement('code');
        code.textContent = part.slice(1, -1);
        return code;
      }
      return document.createTextNode(part);
    }));
  }
  function reset() {
    cancelMotion();
    const sample = cases[Number(selector.value)];
    renderText(documentText, sample.task.document);
    renderText(claimText, sample.task.claim);
    if (panel && panel.animate && motionAllowed()) {
      animation = panel.animate(
        [{ transform: 'translateY(10px)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1 }],
        { duration: 340, easing: 'cubic-bezier(.2,.7,.3,1)' });
      const current = animation;
      current.onfinish = () => { if (animation === current) animation = null; };
    }
    choices.forEach(button => button.setAttribute('aria-pressed', 'false'));
    feedback.dataset.verdict = '';
    feedback.textContent = '选择一个动作，查看编辑标签与理由。';
  }
  choices.forEach(button => button.addEventListener('click', () => {
    const sample = cases[Number(selector.value)];
    const accepted = sample.acceptable.includes(button.dataset.action);
    choices.forEach(choice => choice.setAttribute('aria-pressed', String(choice === button)));
    feedback.dataset.verdict = accepted ? 'accept' : 'reject';
    const heading = document.createElement('strong');
    heading.textContent = accepted ? '这是编辑标签接受的一种动作。' : '这个动作不在本例的可接受标签中。';
    feedback.replaceChildren(heading, document.createTextNode(sample.rationale));
  }));
  selector.addEventListener('change', reset);
  document.querySelector('.case-selector').hidden = false;
  document.querySelector('.exercise-actions').hidden = false;
  reset();
})();
