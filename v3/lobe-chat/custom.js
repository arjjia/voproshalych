(function () {
  'use strict';
  var BRAND = '#00aeef';

  function addCSS() {
    if (document.getElementById('vop-style')) return;
    var s = document.createElement('style');
    s.id = 'vop-style';
    s.textContent = [
      'a[href="https://github.com/lobehub/lobe-chat"],a[aria-label="GitHub"]{display:none!important}',
      'a[href="/labs"],a[aria-label="\u041B\u0430\u0431\u043E\u0440\u0430\u0442\u043E\u0440\u0438\u044F"]{display:none!important}',
      '.model-switch{display:none!important}',
      '.lobe-model-info-tags{display:none!important}',
      '.ant-draggable-panel-toggle-left,.ant-draggable-panel-left-handle{display:none!important}',
      'footer,.ant-layout-footer,[class*="footer"]{display:none!important}',
      ':root{--brand:' + BRAND + ';--primary:' + BRAND + '}',
      '[class*="primary"],[class*="accent"]{accent-color:' + BRAND + '}',
      '.ant-btn-primary{background:' + BRAND + '!important;border-color:' + BRAND + '!important}',
      'a{color:' + BRAND + '!important}',
      '[class*="logo"]{filter:hue-rotate(0deg)}',
    ].join(' ');
    document.head.appendChild(s);
  }

  function has(el, txt) {
    return el.textContent.indexOf(txt) !== -1;
  }

  function hide(el) {
    if (el && el.style && el.style.display !== 'none') {
      el.style.display = 'none';
    }
  }

  function clean() {
    document.querySelectorAll('aside.ant-draggable-panel').forEach(function (a) {
      if (has(a, '\u0444\u0430\u0439\u043B\u044B') || has(a, '\u043F\u043B\u0430\u0433\u0438\u043D\u044B') || has(a, '\u0422\u0435\u043C\u0430')) {
        hide(a);
      }
    });

    document.querySelectorAll('button').forEach(function (b) {
      var t = b.textContent.trim();
      if (t === '\u0421\u043E\u0437\u0434\u0430\u0442\u044C \u043F\u043E\u043C\u043E\u0449\u043D\u0438\u043A\u0430' || t.indexOf('\u0418\u0441\u043F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u043D\u043E') === 0) {
        hide(b);
      }
    });

    document.querySelectorAll('[class*="model-tag"],[class*="provider-tag"]').forEach(hide);

    document.querySelectorAll('[aria-label*="\u0442\u0435\u043C\u0443"],[aria-label*="\u0442\u0435\u043C\u044B"],[aria-label*="topic"]').forEach(hide);
  }

  addCSS();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', clean);
  } else {
    clean();
  }

  var waitBody = setInterval(function () {
    if (document.body) {
      new MutationObserver(clean).observe(document.body, {
        childList: true,
        subtree: true,
      });
      clearInterval(waitBody);
    }
  }, 50);
})();
