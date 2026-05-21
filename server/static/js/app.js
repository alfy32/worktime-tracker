const App = (() => {
  const PAGES = ['dashboard', 'daily', 'weekly', 'log'];
  let refreshTimer = null;

  function showTab(name) {
    if (!PAGES.includes(name)) name = 'dashboard';

    PAGES.forEach(p => {
      const el = document.getElementById('page-' + p);
      el.classList.toggle('active', p === name);
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
      const active = btn.dataset.tab === name;
      btn.classList.toggle('bg-slate-700',    active);
      btn.classList.toggle('text-slate-200',  active);
      btn.classList.toggle('text-slate-400',  !active);
      btn.classList.toggle('hover:text-slate-200', !active);
    });

    clearInterval(refreshTimer);

    if (name === 'dashboard') {
      Dashboard.load();
      refreshTimer = setInterval(() => Dashboard.load(), 30000);
    } else if (name === 'daily') {
      Daily.load();
    } else if (name === 'weekly') {
      Weekly.load();
    } else if (name === 'log') {
      Log.load();
    }

    history.replaceState(null, '', '#' + name);
  }

  function init() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => showTab(btn.dataset.tab));
    });
    const hash = location.hash.replace('#', '');
    showTab(PAGES.includes(hash) ? hash : 'dashboard');
  }

  return { init, showTab };
})();

document.addEventListener('DOMContentLoaded', () => App.init());
