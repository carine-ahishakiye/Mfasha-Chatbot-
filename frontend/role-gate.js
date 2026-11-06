(function () {
  'use strict';
  var KEY = 'mfasha-role';
  var role = null;
  try { role = sessionStorage.getItem(KEY); } catch (e) {}
  if (role === 'farmer') return;                       // already chose farmer in this session
  if (role === 'officer') { location.replace('officer.html'); return; }

  var css = document.createElement('style');
  css.textContent =
    '.rg{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:20px;background:var(--bg,#F6F4EC);overflow:auto}' +
    '.rg-box{width:100%;max-width:520px;text-align:center}' +
    '.rg-box svg{width:56px;height:56px}' +
    '.rg-box h1{margin:12px 0 4px;font-family:var(--serif,Georgia,serif);font-size:2rem;font-weight:500}' +
    '.rg-box p{margin:0 0 24px;color:var(--muted,#566058)}' +
    '.rg-opts{display:grid;gap:12px}' +
    '.rg-opt{display:flex;flex-direction:column;gap:2px;align-items:flex-start;text-align:left;width:100%;min-height:76px;padding:16px 18px;' +
      'border:1px solid var(--border,#E3DFD0);border-radius:12px;background:#fff;cursor:pointer}' +
    '.rg-opt:hover{border-color:var(--primary,#2E7D32);background:var(--primary-light,#E8F5E9)}' +
    '.rg-opt strong{font-size:1.05rem;font-weight:500}' +
    '.rg-opt span{font-size:.88rem;color:var(--muted,#566058)}';
  document.head.appendChild(css);

  var gate = document.createElement('div');
  gate.className = 'rg'; gate.setAttribute('role', 'dialog'); gate.setAttribute('aria-modal', 'true');
  gate.setAttribute('aria-labelledby', 'rg-title');
  gate.innerHTML =
    '<div class="rg-box">' +
      '<svg viewBox="0 0 120 120" aria-hidden="true"><use href="#logo-mark"/></svg>' +
      '<h1 id="rg-title">Murakaza neza kuri Mfasha</h1>' +
      '<p>Uri nde?</p>' +
      '<div class="rg-opts">' +
        '<button type="button" class="rg-opt" data-role="farmer"><strong>Ndi umuhinzi</strong><span>Baza ibibazo ku buhinzi n’ubworozi</span></button>' +
        '<button type="button" class="rg-opt" data-role="officer"><strong>Ndi umukozi w’ubuhinzi</strong><span>Suzuma ibisubizo kandi ukurikirane imikorere</span></button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(gate);
  gate.querySelector('[data-role="farmer"]').focus();

  gate.addEventListener('click', function (e) {
    var b = e.target.closest('[data-role]');
    if (!b) return;
    var chosen = b.getAttribute('data-role');
    try { sessionStorage.setItem(KEY, chosen); } catch (err) {}
    if (chosen === 'officer') { location.href = 'officer.html'; return; }
    gate.remove();
  });
}());