(function () {
  var selects = document.querySelectorAll('#filters select');
  var claims = document.querySelectorAll('.claim');
  var shown = document.getElementById('shown');
  function apply() {
    var active = {};
    selects.forEach(function (s) { if (s.value) active[s.dataset.filter] = s.value; });
    var n = 0;
    claims.forEach(function (c) {
      var ok = Object.keys(active).every(function (k) { return c.dataset[k] === active[k]; });
      c.hidden = !ok; if (ok) n++;
    });
    shown.textContent = 'Showing ' + n + ' of ' + claims.length;
  }
  selects.forEach(function (s) { s.addEventListener('change', apply); });
  apply();
})();
