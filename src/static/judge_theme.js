(() => {
  const toggle = document.querySelector('.rg-theme-toggle');
  if (!toggle) return;
  const root = document.documentElement;
  function update() {
    const dark = root.dataset.theme === 'dark';
    toggle.setAttribute('aria-pressed', String(dark));
    toggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
    toggle.title = dark ? 'Light mode' : 'Dark mode';
    toggle.querySelector('span').textContent = dark ? 'L' : 'D';
  }
  update();
  toggle.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('rg-theme', root.dataset.theme); } catch (error) { /* Temporary choice still works. */ }
    update();
  });
})();
