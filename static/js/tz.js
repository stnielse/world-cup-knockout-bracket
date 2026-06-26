(function () {
    const fmt = new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });

    function relocalize(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('time[datetime]').forEach(function (el) {
            if (el.dataset.tzApplied === '1') return;
            const d = new Date(el.getAttribute('datetime'));
            if (isNaN(d.getTime())) return;
            el.textContent = fmt.format(d);
            el.dataset.tzApplied = '1';
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { relocalize(); });
    } else {
        relocalize();
    }

    document.body.addEventListener('htmx:afterSwap', function (evt) {
        relocalize(evt.target);
    });
})();
