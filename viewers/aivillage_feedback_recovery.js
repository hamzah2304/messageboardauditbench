// Repair anonymous browser-queued feedback, then let ui-kit perform its usual
// sync. Existing reviewer names, comment bodies, anchors and event IDs survive.
window.recoverAnonymousFeedback = async function () {
  const segments = location.pathname.split('/').filter(Boolean);
  const rootSegments = segments[0] === '_s' ? segments.slice(0, 3) : segments.slice(0, 1);
  const pendingKey = 'uikit:pending:/' + rootSegments.join('/') + '/';
  const validName = name => typeof name === 'string' && name.trim().length > 0 && name.trim().length <= 100;
  let queue;
  try { queue = JSON.parse(localStorage.getItem(pendingKey) || '[]'); }
  catch { return; }
  if (!Array.isArray(queue) || !queue.some(event => !validName(event.rater))) return;
  let supplied = new URLSearchParams(location.search).get('rater');
  if (!validName(supplied)) {
    try { supplied = JSON.parse(localStorage.getItem('uikit:rater') || 'null'); }
    catch { supplied = null; }
  }
  if (!validName(supplied)) {
    supplied = await new Promise(resolve => {
      const panel = document.createElement('form');
      panel.setAttribute('role', 'alert');
      panel.style.cssText = 'position:fixed;inset:0;z-index:10001;background:#fffffff5;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:24px';
      const message = document.createElement('p');
      message.textContent = 'Your queued comments have no reviewer name. Enter your name to resend them. Their text will be preserved.';
      const name = document.createElement('input');
      name.placeholder = 'Your name'; name.maxLength = 100; name.required = true;
      name.setAttribute('aria-label', 'Reviewer name for queued comments');
      const button = document.createElement('button');
      button.textContent = 'Resend my comments'; button.type = 'submit';
      panel.append(message, name, button); document.body.append(panel); name.focus();
      panel.onsubmit = event => { event.preventDefault(); if (validName(name.value)) { panel.remove(); resolve(name.value.trim()); } };
    });
  }
  const name = supplied.trim();
  const repair = () => {
    const latest = JSON.parse(localStorage.getItem(pendingKey) || '[]');
    const repaired = latest.map(event => validName(event.rater) ? event : {...event, rater: name});
    // If storage fails, leave the original pending queue intact and surface the
    // failure. No feedback is removed before ui-kit receives acknowledgement.
    localStorage.setItem(pendingKey, JSON.stringify(repaired));
    localStorage.setItem('uikit:rater', JSON.stringify(name));
  };
  if (navigator.locks) await navigator.locks.request(pendingKey, repair);
  else repair();
};
