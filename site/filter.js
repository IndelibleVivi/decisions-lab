// Progressive enhancement: search project rows; original evidence remains visible.
const input = document.querySelector('#project-filter');
if (input) {
  const filter = document.querySelector('.filter');
  const rows = [...document.querySelectorAll('article table tbody tr')];
  const status = document.querySelector('#filter-result');
  filter.hidden = false;
  const update = () => {
    const query = input.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach(row => {
      row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
      if (!row.hidden) visible++;
    });
    status.textContent = `显示 ${visible} / ${rows.length} 个项目。下方的局限与追踪线索始终保留。`;
  };
  input.addEventListener('input', update);
  update();
}
