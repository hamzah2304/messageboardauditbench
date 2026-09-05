/* Site behaviour: rail highlighting, carousels, TODO toggle. No dependencies. */
(function () {
  'use strict';

  /* ---- left rail: highlight the section in view ---- */
  function initRail() {
    var links = Array.prototype.slice.call(document.querySelectorAll('.rail a[href^="#"]'));
    if (!links.length) return;
    var map = {};
    links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
    var secs = Object.keys(map).map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var current = null;
    function setActive(id) {
      if (id === current) return;
      current = id;
      links.forEach(function (a) { a.classList.toggle('active', a.getAttribute('href') === '#' + id); });
      // keep the parent section lit while a subsection is active
      var act = document.querySelector('.rail a.active');
      if (act) { var parentLi = act.closest('ol').closest('li'); var pa = parentLi && parentLi.querySelector(':scope > a'); if (pa && pa !== act) pa.classList.add('active'); }
    }
    function top(el) { return el.getBoundingClientRect().top + window.scrollY; }
    function update() {
      var y = window.scrollY + Math.min(200, window.innerHeight * 0.3);
      var best = secs[0];
      for (var i = 0; i < secs.length; i++) { if (top(secs[i]) <= y) best = secs[i]; }
      if (best) setActive(best.id);
    }
    var inner = document.querySelector('.rail-inner');
    function measure() { if (inner) inner.style.setProperty('--rail-h', inner.offsetHeight + 'px'); }
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', function () { measure(); update(); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);
    measure(); update();
  }

  /* ---- carousels ---- */
  // The view is a scroll-snap container and every slide sits in it unhidden, so the
  // browser's find-in-page matches text on slides that are not showing and scrolls to
  // them itself. Paging is therefore just a scroll, and the scroll position — however it
  // moved, by button, swipe or Cmd+F — is what the dots and the counter read.
  function initCarousel(root) {
    var view = root.querySelector('.carousel-view');
    var slides = Array.prototype.slice.call(root.querySelectorAll('.slide'));
    var prev = root.querySelector('[data-prev]');
    var next = root.querySelector('[data-next]');
    var counter = root.querySelector('[data-counter]');
    var dotsBox = root.querySelector('.dots');
    var i = 0, n = slides.length;
    if (!view || !n) return;

    var dots = [];
    if (dotsBox) {
      slides.forEach(function (_, k) {
        var b = document.createElement('button');
        b.type = 'button';
        b.setAttribute('aria-label', 'Go to item ' + (k + 1));
        b.addEventListener('click', function () { go(k); });
        dotsBox.appendChild(b); dots.push(b);
      });
    }
    var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
    function go(k) {
      i = Math.max(0, Math.min(n - 1, k));
      view.scrollTo({ left: slides[i].offsetLeft, behavior: still && still.matches ? 'auto' : 'smooth' });
      render();
    }
    function settled() {
      // wherever the scroll came to rest — a swipe, a Cmd+F match, a focused link —
      // that slide is the one we are on
      var w = view.clientWidth;
      i = w ? Math.max(0, Math.min(n - 1, Math.round(view.scrollLeft / w))) : 0;
      render();
    }
    function render() {
      if (prev) prev.disabled = i === 0;
      if (next) next.disabled = i === n - 1;
      if (counter) counter.textContent = (i + 1) + ' / ' + n;
      dots.forEach(function (d, k2) { if (k2 === i) d.setAttribute('aria-current', 'true'); else d.removeAttribute('aria-current'); });
    }
    function fit() {
      // fixed depth: the view is as tall as the tallest slide, so paging never
      // moves the page around; an expanded "whole post" can still grow it
      var h = 0;
      slides.forEach(function (s) { h = Math.max(h, s.offsetHeight); });
      view.style.height = h ? h + 'px' : '';
    }
    // a "Show the whole post" toggle inside a slide changes its height
    root.addEventListener('change', function (e) { if (e.target.classList.contains('ex-toggle')) fit(); });
    // read the position only once it stops moving, so the halfway point of a smooth
    // scroll never lights the wrong dot and a fast second click still advances
    var rest = null;
    view.addEventListener('scroll', function () {
      clearTimeout(rest);
      rest = setTimeout(settled, 120);
    }, { passive: true });
    // tabbing reaches the links on every slide now, so follow focus to its slide
    view.addEventListener('focusin', function (e) {
      var s = e.target.closest && e.target.closest('.slide');
      var k = s ? slides.indexOf(s) : -1;
      if (k >= 0 && k !== i) go(k);
    });
    if (prev) prev.addEventListener('click', function () { go(i - 1); });
    if (next) next.addEventListener('click', function () { go(i + 1); });
    root.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') { go(i - 1); e.preventDefault(); }
      if (e.key === 'ArrowRight') { go(i + 1); e.preventDefault(); }
    });
    // snapping keeps the same slide across a resize; only the height needs redoing
    window.addEventListener('resize', fit);
    slides.forEach(function (s) {
      Array.prototype.forEach.call(s.querySelectorAll('img'), function (img) { img.addEventListener('load', fit); });
    });
    fit(); settled();
    // re-measure once fonts have settled
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
    setTimeout(fit, 300);
  }

  /* ---- TODO visibility toggle (for the team; strip before publishing) ---- */
  function initTodoToggle() {
    var btn = document.querySelector('.todo-toggle');
    if (!btn) return;
    var key = 'wiki-swarm-hide-todos';
    var hidden = false;
    try { hidden = localStorage.getItem(key) === '1'; } catch (e) {}
    function apply() {
      document.body.classList.toggle('hide-todos', hidden);
      var n = document.querySelectorAll('aside.todo, .draft, mark.todo-inline, .sidenote.todo-note').length;
      btn.textContent = (hidden ? 'Show' : 'Hide') + ' ' + n + ' analysis TODOs';
      btn.setAttribute('aria-pressed', hidden ? 'true' : 'false');
    }
    btn.addEventListener('click', function () {
      hidden = !hidden;
      try { localStorage.setItem(key, hidden ? '1' : '0'); } catch (e) {}
      apply();
    });
    apply();
  }

  /* ---- footnotes as hovernotes ---- */
  function initHovernotes() {
    var essay = document.querySelector('.essay');
    if (!essay) return;
    var openNote = null, openLabel = null, pinned = false, hideTimer = null;
    function place(label, note) {
      note.classList.add('open');
      // the note is absolutely positioned against its nearest positioned ancestor, which is
      // the essay for most footnotes but a list item for the summary list's, so measure that
      var op = note.offsetParent || essay;
      var er = op.getBoundingClientRect();
      var lr = label.getBoundingClientRect();
      var w = note.offsetWidth;
      var left = lr.left - er.left - 12;
      var maxLeft = op.clientWidth - w - 4;
      if (left > maxLeft) left = maxLeft;
      if (left < 0) left = 0;
      var top = lr.bottom - er.top + 6;
      note.style.left = left + 'px';
      note.style.top = top + 'px';
    }
    function show(label, note) {
      if (openNote && openNote !== note) hide();
      clearTimeout(hideTimer);
      openNote = note; openLabel = label;
      label.classList.add('on');
      // aria-expanded belongs here and in hide(), the two places the note's visibility changes
      label.setAttribute('aria-expanded', 'true');
      place(label, note);
    }
    function hide() {
      if (!openNote) return;
      openNote.classList.remove('open');
      openLabel.classList.remove('on');
      openLabel.setAttribute('aria-expanded', 'false');
      openNote = null; openLabel = null; pinned = false;
    }
    function scheduleHide() {
      if (pinned) return;
      clearTimeout(hideTimer);
      hideTimer = setTimeout(hide, 220);
    }
    Array.prototype.forEach.call(document.querySelectorAll('label.sidenote-number'), function (label) {
      var input = document.getElementById(label.getAttribute('for'));
      var note = input && input.nextElementSibling;
      if (!note || !note.classList.contains('sidenote')) return;
      label.setAttribute('tabindex', '0');
      label.setAttribute('role', 'button');
      label.setAttribute('aria-expanded', 'false');
      // the note ships without an id, and aria-controls has to name one; the checkbox's is unique
      if (!note.id) note.id = input.id + '-note';
      label.setAttribute('aria-controls', note.id);
      label.addEventListener('mouseenter', function () { if (!pinned) show(label, note); });
      label.addEventListener('mouseleave', scheduleHide);
      label.addEventListener('focus', function () { show(label, note); });
      label.addEventListener('blur', scheduleHide);
      function pin() {
        if (openNote === note && pinned) { hide(); return; }
        show(label, note); pinned = true;
      }
      label.addEventListener('click', function (e) { e.preventDefault(); pin(); });
      // a label is not a button: it answers the pointer but not the keys role=button promises
      label.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        pin();
      });
      note.addEventListener('mouseenter', function () { clearTimeout(hideTimer); });
      note.addEventListener('mouseleave', scheduleHide);
    });
    document.addEventListener('click', function (e) {
      if (!openNote) return;
      if (openNote.contains(e.target) || openLabel.contains(e.target)) return;
      hide();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hide(); });
    window.addEventListener('resize', function () { if (openNote) place(openLabel, openNote); });
  }

  /* ---- the bar's menu: below 700px chrome.css makes it the hamburger for the whole bar, and a
          menu has to close on a click past it and on Escape. Over on the explorer half only
          analysis.html closes it on an outside click, and nothing there answers Escape; that is
          the generator's to fix, and this is the write-up's side of it. ---- */
  function initNavMenu() {
    var menu = document.querySelector('.chrome .nav-more');
    if (!menu) return;
    document.addEventListener('click', function (e) {
      if (menu.open && !menu.contains(e.target)) menu.open = false;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape' || !menu.open) return;
      menu.open = false;
      var summary = menu.querySelector('summary');
      if (summary) summary.focus();
    });
  }

  /* ---- "Show the whole post": open the card and put its start where the reader can see it ----
          The disclosure is a label driving a hidden checkbox, and clicking a label focuses its
          control; a focus target the pinned bar covers is not "visible", so the browser centres it
          in the window -- a 450-550px jump when the card's top had only just left the top of the
          screen. So toggle the box here instead of letting the label do it, and then scroll only if
          the card's start is under the bar or off the top, and only as far as scroll-padding-top's
          landing spot. Without this file the label still works, and styles.css parks the box at the
          card's foot to keep that fallback's jump small. */
  function initExcerpts() {
    document.addEventListener('click', function (e) {
      var label = e.target.closest('label.ex-more');
      var box = label && document.getElementById(label.getAttribute('for'));
      if (!box) return;
      e.preventDefault();
      box.checked = !box.checked;
      box.dispatchEvent(new Event('change', { bubbles: true }));
    });
    document.addEventListener('change', function (e) {
      if (!e.target.classList.contains('ex-toggle') || !e.target.checked) return;
      var card = e.target.closest('figure.ex');
      var pad = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
      if (card && card.getBoundingClientRect().top < pad) card.scrollIntoView({ block: 'start' });
    });
  }

  /* ---- folded sections: open the one a link points at, refit widgets on toggle ---- */
  function initFolds() {
    var folds = Array.prototype.slice.call(document.querySelectorAll('details.fact'));
    if (!folds.length) return;
    folds.forEach(function (d) {
      d.addEventListener('toggle', function () { window.dispatchEvent(new Event('resize')); });
    });
    function openFor(hash) {
      if (!hash || hash.length < 2) return;
      var el = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (!el) return;
      /* A whole folded section (details.whole) is its section's only child, so the link the rail
         and the contents carry points at the section, not into the fold: open it from outside. */
      var d = el.closest('details.fact') || el.querySelector(':scope > details.whole');
      if (d && !d.open) { d.open = true; setTimeout(function () { el.scrollIntoView({ block: 'start' }); }, 0); }
    }
    window.addEventListener('hashchange', function () { openFor(location.hash); });
    document.addEventListener('click', function (e) {
      var a = e.target.closest('a[href^="#"]');
      if (a) openFor(a.getAttribute('href'));
    });
    openFor(location.hash);
  }

  document.addEventListener('DOMContentLoaded', function () {
    initFolds();
    initExcerpts();
    initHovernotes();
    initNavMenu();
    initRail();
    Array.prototype.forEach.call(document.querySelectorAll('.carousel'), initCarousel);
  });
})();
