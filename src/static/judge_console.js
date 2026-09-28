/* Progressive enhancement: explicit POST works with JavaScript disabled. */
(() => {
  const form = document.getElementById('rg-score-form');
  if (!form) return;
  const state = document.querySelector('.rg-save-state');
  const feedback = document.querySelector('.rg-feedback');
  const button = form.querySelector('button[type="submit"]');
  let timer = null, saving = false, version = 0, acknowledged = 0;
  let pendingDestination = null;
  let allowNavigation = false;
  let submitThenNext = false;
  let persistAcknowledged = !!form.dataset.saved;
  let dirty = false;
  function status(text, className = '') {
    state.textContent = text;
    state.className = 'rg-save-state ' + className;
  }
  async function save() {
    clearTimeout(timer);
    if (saving || !dirty || !form.checkValidity()) return;
    saving = true; button.disabled = true;
    const sentVersion = version;
    status('Saving...', 'is-pending'); feedback.textContent = '';
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `Save failed (${response.status})`);
      }
      acknowledged = sentVersion;
      persistAcknowledged = true;
      dirty = version !== acknowledged;
      if (version === acknowledged) status('Saved at ' + new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}), 'is-saved');
      else status('Saving newer changes...', 'is-pending');
    } catch (error) {
      submitThenNext = false;
      status("Couldn't save - Retry", 'is-failed');
      feedback.textContent = error.message;
    } finally {
      saving = false; button.disabled = false;
      if (dirty && !feedback.textContent) timer = setTimeout(save, 100);
      if (submitThenNext && !dirty && persistAcknowledged) {
        submitThenNext = false;
        const next = document.querySelector('[data-next-project]');
        if (next) { pendingDestination = null; allowNavigation = true; window.location.assign(next.href); }
      }
      if (pendingDestination && !dirty && persistAcknowledged && !submitThenNext) { const target = pendingDestination; pendingDestination = null; allowNavigation = true; window.location.assign(target); }
    }
  }
  form.addEventListener('input', () => {
    version += 1; dirty = true;
    status('Unsaved changes', 'is-pending');
    clearTimeout(timer);
    timer = setTimeout(save, 700);
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    submitThenNext = !!document.querySelector('[data-next-project]');
    if (saving) return;
    if (!dirty && persistAcknowledged && submitThenNext) { allowNavigation = true; window.location.assign(document.querySelector('[data-next-project]').href); return; }
    version += 1; dirty = true;
    await save();
  });
  document.querySelectorAll('a[href*="/judge/console/"]').forEach((link) => {
    link.addEventListener('click', async (event) => {
      if (!dirty && !saving && persistAcknowledged) return;
      event.preventDefault();
      pendingDestination = link.href;
      if (!form.reportValidity()) { pendingDestination = null; feedback.textContent = 'Score every criterion before changing projects.'; return; }
      if (!persistAcknowledged && !dirty) { version += 1; dirty = true; }
      if (!saving) await save();
      if (dirty && feedback.textContent) pendingDestination = null;
    });
  });
  window.addEventListener('beforeunload', (event) => {
    if (!allowNavigation && (dirty || saving)) { event.preventDefault(); event.returnValue = ''; }
  });
})();
