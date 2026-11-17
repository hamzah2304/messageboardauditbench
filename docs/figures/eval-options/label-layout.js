/* Save draggable SVG label positions through the same ui-kit store as other reviews. */
(async () => {
  const message = document.getElementById('layout-message');
  try {
    const kit = await UIKit.init({comments: false});
    const response = await fetch('performance-vs-cost.svg', {cache: 'no-cache'});
    if (!response.ok) throw new Error(`Figure returned HTTP ${response.status}`);
    const doc = new DOMParser().parseFromString(await response.text(), 'image/svg+xml');
    if (doc.querySelector('parsererror')) throw new Error('Could not read the figure');
    const svg = document.importNode(doc.documentElement, true);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Performance versus cost. Model labels can be dragged or moved with arrow keys.');
    document.getElementById('cost-interactive').replaceChildren(svg);
    const layoutResponse = await fetch('label-layout.json', {cache: 'no-cache'});
    if (!layoutResponse.ok) throw new Error('Could not load the approved label layout');
    const approved = (await layoutResponse.json()).positions;
    const KEY = 'cost-label-layout-v1';
    const labels = new Map();
    let drag = null;
    for (const group of svg.querySelectorAll('[id^="model-label-"]')) {
      const text = group.querySelector('text');
      const leader = svg.querySelector(`#${group.id.replace('model-label-', 'model-leader-')} path`);
      const coordinates = leader.getAttribute('d').match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi).map(Number);
      labels.set(group.id, {text, leader, x: Number(text.getAttribute('x')), y: Number(text.getAttribute('y')),
        originalPath: leader.getAttribute('d'), end: coordinates.slice(-2)});
      text.setAttribute('tabindex', '0');
      text.setAttribute('aria-label', `Move ${text.textContent} label`);
      text.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        event.preventDefault();
        text.focus();
        const point = screenPoint(event);
        drag = {id: group.id, pointer: event.pointerId, start: point,
          x: Number(text.getAttribute('x')), y: Number(text.getAttribute('y'))};
        text.setPointerCapture(event.pointerId);
        text.style.cursor = 'grabbing';
      });
      text.addEventListener('pointermove', event => {
        if (!drag || drag.id !== group.id || drag.pointer !== event.pointerId) return;
        const point = screenPoint(event);
        move(group.id, drag.x + point.x - drag.start.x, drag.y + point.y - drag.start.y);
      });
      text.addEventListener('pointerup', async event => {
        if (!drag || drag.id !== group.id || drag.pointer !== event.pointerId) return;
        drag = null;
        text.style.cursor = 'grab';
        if (text.hasPointerCapture(event.pointerId)) text.releasePointerCapture(event.pointerId);
        await persist();
      });
      text.addEventListener('pointercancel', () => {drag = null; text.style.cursor = 'grab'; restore();});
      text.addEventListener('keydown', async event => {
        const directions = {ArrowLeft: [-1,0], ArrowRight: [1,0], ArrowUp: [0,-1], ArrowDown: [0,1]};
        if (!directions[event.key]) return;
        event.preventDefault();
        const [dx,dy] = directions[event.key], step = event.shiftKey ? 10 : 2;
        move(group.id, Number(text.getAttribute('x'))+dx*step, Number(text.getAttribute('y'))+dy*step);
        await persist();
      });
    }
    function screenPoint(event) {
      return new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
    }
    function move(id, x, y) {
      const label = labels.get(id), box = svg.viewBox.baseVal;
      x = Math.max(5, Math.min(box.width-5, x));
      y = Math.max(12, Math.min(box.height-5, y));
      label.text.setAttribute('x', x); label.text.setAttribute('y', y);
      // Text is unrotated in this figure, so the old zero-degree transform is redundant.
      label.text.removeAttribute('transform');
      let b = label.text.getBBox();
      const shiftX = Math.max(4-b.x, Math.min(0, box.width-4-b.x-b.width));
      const shiftY = Math.max(4-b.y, Math.min(0, box.height-4-b.y-b.height));
      if (shiftX || shiftY) {
        label.text.setAttribute('x', x+shiftX); label.text.setAttribute('y', y+shiftY);
        b = label.text.getBBox();
      }
      const [ex,ey] = label.end;
      const sx = Math.max(b.x, Math.min(b.x+b.width, ex));
      const sy = Math.max(b.y, Math.min(b.y+b.height, ey));
      label.leader.setAttribute('d', `M ${sx} ${sy} L ${ex} ${ey}`);
    }
    function restore() {
      const saved = kit.get(KEY)?.positions || {};
      for (const [id,label] of labels) {
        const offset = saved[id];
        if (offset && Number.isFinite(offset.dx) && Number.isFinite(offset.dy)) {
          move(id, label.x+offset.dx-approved[id].dx, label.y+offset.dy-approved[id].dy);
        } else {
          label.text.setAttribute('x', label.x); label.text.setAttribute('y', label.y);
          label.leader.setAttribute('d', label.originalPath);
        }
      }
    }
    async function persist() {
      const positions = {};
      for (const [id,label] of labels) positions[id] = {
        dx: Number(label.text.getAttribute('x'))-label.x+approved[id].dx,
        dy: Number(label.text.getAttribute('y'))-label.y+approved[id].dy};
      await kit.save(KEY, {...(kit.get(KEY) || {}), positions});
    }
    kit.onChange(key => {if (!drag && (!key || key === KEY)) restore();});
    restore();
    const reset = document.getElementById('reset-labels'); reset.disabled = false;
    reset.onclick = async () => {await kit.save(KEY, {...(kit.get(KEY) || {}), positions: {}}); restore();};
    const download = document.getElementById('download-layout'); download.disabled = false;
    download.onclick = () => {
      const clone = svg.cloneNode(true);
      for (const text of clone.querySelectorAll('text')) {text.removeAttribute('tabindex'); text.style.removeProperty('cursor');}
      const blob = new Blob([new XMLSerializer().serializeToString(clone)], {type: 'image/svg+xml'});
      const url = URL.createObjectURL(blob), a = document.createElement('a');
      a.href = url; a.download = 'performance-vs-cost-adjusted.svg'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    message.textContent = 'Drag a label; changes save under your name.';
  } catch (error) {
    message.textContent = `Could not enable label editing: ${error.message}`;
  }
})();
