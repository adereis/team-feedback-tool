/**
 * Butterfly chart: one row per tenet, improvements growing left from the
 * tenet name and strengths growing right, each bar labeled with its count.
 * Plain HTML/CSS bars (styles in style.css under .butterfly), so the chart
 * needs no charting library, works offline and reflows on narrow screens.
 *
 * Rows come from reports.py (Tally.butterfly): [{id, name, strength_count,
 * improvement_count}], already in display order. The PDF draws its own
 * chart with matplotlib (app.py).
 *
 * tests/test_butterfly.py runs layout() and withPicks() under Node.
 */
(function (root) {
    /**
     * What to draw for each row: bar widths as a percentage of the longest
     * bar (both sides share one scale, so lengths compare across the axis).
     * @param {Array} rows - [{id, name, strength_count, improvement_count}]
     * @param {Object} [picks] - {strengths: [ids], improvements: [ids]} to highlight
     */
    function layout(rows, picks) {
        picks = picks || {};
        const strengths = picks.strengths || [];
        const improvements = picks.improvements || [];
        const max = Math.max(1, ...rows.map(r => Math.max(r.strength_count, r.improvement_count)));
        return rows.map(r => ({
            id: r.id,
            name: r.name,
            strength: {
                count: r.strength_count,
                width: 100 * r.strength_count / max,
                picked: strengths.includes(r.id)
            },
            improvement: {
                count: r.improvement_count,
                width: 100 * r.improvement_count / max,
                picked: improvements.includes(r.id)
            }
        }));
    }

    /**
     * Move the manager's +1 from the saved picks to the current ones.
     *
     * The server's counts include the picks saved when the page loaded. While
     * the manager changes picks, each saved pick gives its +1 back and each
     * current pick adds one, so a highlighted bar always includes its pick.
     * Row order is kept, so bars do not jump around while picking.
     */
    function withPicks(rows, saved, current) {
        const delta = (list, id) => (current[list].includes(id) ? 1 : 0) - (saved[list].includes(id) ? 1 : 0);
        return rows.map(r => Object.assign({}, r, {
            strength_count: r.strength_count + delta('strengths', r.id),
            improvement_count: r.improvement_count + delta('improvements', r.id)
        }));
    }

    function escapeText(value) {
        const div = document.createElement('div');
        div.textContent = value;
        return div.innerHTML;
    }

    function plural(count, word) {
        return `${count} ${word}${count === 1 ? '' : 's'}`;
    }

    // One side of a row: the bar, then its count at the bar's tip. The bar's
    // width leaves room for the count, so the longest bar still fits.
    function side(kind, bar) {
        const star = bar.picked ? '<span class="bf-star" aria-hidden="true">★</span>' : '';
        const spoken = `<span class="sr-only"> ${kind === 'strength' ? 'strength' : 'improvement'}` +
            `${bar.count === 1 ? '' : 's'}${bar.picked ? ', highlighted' : ''}</span>`;
        return `<div class="bf-side bf-${kind}${bar.picked ? ' picked' : ''}">` +
            `<span class="bf-bar" style="width: calc((100% - var(--bf-count-space)) * ${bar.width / 100})"></span>` +
            `<span class="bf-count${bar.count ? '' : ' zero'}">${bar.count}${star}${spoken}</span></div>`;
    }

    /**
     * Draw the chart into container, replacing its content.
     * @param {Element} container
     * @param {Array} rows - as for layout()
     * @param {Object} [picks] - tenets to highlight (the manager's picks)
     */
    function render(container, rows, picks) {
        if (!rows || rows.length === 0) {
            container.innerHTML = '<p class="empty-note">No feedback data available yet.</p>';
            return;
        }
        const body = layout(rows, picks).map(r =>
            `<div class="bf-row" title="${escapeText(r.name)}: ${plural(r.strength.count, 'strength')}, ${plural(r.improvement.count, 'improvement')}">` +
            side('improvement', r.improvement) +
            `<div class="bf-label">${escapeText(r.name)}</div>` +
            side('strength', r.strength) +
            '</div>'
        ).join('');
        container.innerHTML =
            '<div class="butterfly">' +
            '<div class="bf-row bf-head" aria-hidden="true"><span class="bf-improvement">← Improvements</span>' +
            '<span class="bf-label"></span><span class="bf-strength">Strengths →</span></div>' +
            body + '</div>';
    }

    const api = { layout: layout, withPicks: withPicks, render: render };
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;  // Node (tests)
    } else {
        root.Butterfly = api;
    }
})(this);
