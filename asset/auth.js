'use strict';

(() => {
  const form = document.querySelector('#auth-form');
  const title = document.querySelector('#auth-title');
  const description = document.querySelector('#auth-description');
  const feedback = document.querySelector('#auth-feedback');
  const submit = form.querySelector('[type=submit]');
  const submitLabel = document.querySelector('#auth-submit-label');
  const name = document.querySelector('#auth-name');
  const phone = document.querySelector('#auth-phone');
  const email = document.querySelector('#auth-email');
  const password = document.querySelector('#auth-password');
  const demo = document.querySelector('.auth-demo');
  const tabs = [...document.querySelectorAll('[data-auth-mode]')];
  const destinations = Object.freeze({customer:'/order',restaurant:'/restaurant',driver:'/driver',admin:'/admin'});
  let mode = 'login';

  function showError(message = '') {
    feedback.textContent = message;
    feedback.hidden = !message;
  }

  function changeMode(next) {
    mode = next === 'register' ? 'register' : 'login';
    const registering = mode === 'register';
    document.querySelector('#auth-name-field').hidden = !registering;
    document.querySelector('#auth-phone-field').hidden = !registering;
    name.disabled = phone.disabled = !registering;
    name.required = registering;
    password.minLength = registering ? 8 : 1;
    password.autocomplete = registering ? 'new-password' : 'current-password';
    password.placeholder = registering ? 'At least 8 characters' : 'Your password';
    form.action = '/api/auth/' + mode;
    title.textContent = registering ? 'Create a customer account' : 'Sign in to Gather';
    description.textContent = registering
      ? 'Create an account to order from local restaurants. Staff should sign in with their work account.'
      : 'One sign-in for customers, restaurant teams, drivers, and administrators.';
    submitLabel.textContent = registering ? 'Create account' : 'Sign in';
    if (demo) demo.hidden = registering;
    tabs.forEach(tab => {
      const active = tab.dataset.authMode === mode;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-pressed', String(active));
    });
    showError();
  }

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetch(path, {credentials:'same-origin', ...options});
    } catch {
      throw new Error('Could not connect to Gather. Check your connection and try again.');
    }
    let data;
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) {
      const detail = data.detail;
      const errors = Array.isArray(detail) ? detail.map(item => {
        const field = (item.loc || []).filter(part => part !== 'body').join(' ');
        return (field ? field + ': ' : '') + (item.msg || 'Check this field.');
      }).join(' ') : detail;
      throw new Error(typeof errors === 'string' && errors ? errors : 'Gather could not sign you in. Try again.');
    }
    return data;
  }

  tabs.forEach(tab => tab.addEventListener('click', () => {
    if (submit.disabled) return;
    if (mode !== tab.dataset.authMode) password.value = '';
    changeMode(tab.dataset.authMode);
    (mode === 'register' ? name : email).focus();
  }));

  document.querySelectorAll('[data-demo-role]').forEach(button => button.addEventListener('click', () => {
    if (submit.disabled || !Object.hasOwn(destinations, button.dataset.demoRole)) return;
    changeMode('login');
    email.value = button.dataset.demoRole + '@localtable.vn';
    password.value = 'Demo123!';
    submit.focus();
  }));

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submit.disabled) return;
    const payload = Object.fromEntries(new FormData(form));
    submit.disabled = true;
    showError();
    submitLabel.textContent = mode === 'register' ? 'Creating account…' : 'Signing in…';
    let navigating = false;
    try {
      const {user} = await request('/api/auth/' + mode, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
      });
      if (!user?.id || !Object.hasOwn(destinations, user.role)) throw new Error('This account has no Gather workspace. Contact an administrator.');
      const session = await request('/api/auth/me');
      if (session.user?.id !== user.id || session.user?.role !== user.role) throw new Error('Your browser did not save the session. Allow cookies for Gather and sign in again.');
      location.replace(destinations[user.role]);
      navigating = true;
    } catch (error) {
      showError(error.message);
    } finally {
      if (!navigating) {
        submit.disabled = false;
        submitLabel.textContent = mode === 'register' ? 'Create account' : 'Sign in';
      }
    }
  });

  window.addEventListener('pagehide', event => { if (event.persisted) document.body.hidden = true; });
  window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
})();
