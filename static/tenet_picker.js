/**
 * Tenet picker shared by the peer pages (/feedback, /individual) and the
 * manager's report page: two grids of tenet buttons, strengths and
 * improvements, plus the selection checklist above them.
 *
 * The rule is the one tenet_selection_error() enforces in app.py: exactly 3
 * strengths, 2-3 improvements, and no tenet in both lists. The picker never
 * lets a selection break the upper limits or the overlap rule; a tenet that
 * cannot be picked is greyed out and says why.
 *
 * tests/test_tenet_picker.py runs toggle(), availability() and status()
 * under Node.
 */
(function (root) {
    const LIMITS = { strengths: { min: 3, max: 3 }, improvements: { min: 2, max: 3 } };
    const OTHER = { strengths: 'improvements', improvements: 'strengths' };
    const NOUN = { strengths: 'strength', improvements: 'improvement' };

    function copy(selection) {
        return { strengths: [...selection.strengths], improvements: [...selection.improvements] };
    }

    /**
     * Whether a tenet can be clicked in one list:
     * 'selected', 'available', 'taken' (picked in the other list) or 'full'.
     */
    function availability(selection, kind, id) {
        if (selection[kind].includes(id)) return 'selected';
        if (selection[OTHER[kind]].includes(id)) return 'taken';
        if (selection[kind].length >= LIMITS[kind].max) return 'full';
        return 'available';
    }

    /** The selection after clicking a tenet in one list (unchanged if not allowed). */
    function toggle(selection, kind, id) {
        const next = copy(selection);
        const state = availability(selection, kind, id);
        if (state === 'selected') {
            next[kind] = next[kind].filter(t => t !== id);
        } else if (state === 'available') {
            next[kind].push(id);
        }
        return next;
    }

    /** Progress toward a valid selection, for the checklist and save logic. */
    function status(selection) {
        const s = selection.strengths.length;
        const i = selection.improvements.length;
        const strengthsDone = s === LIMITS.strengths.min;
        const improvementsDone = i >= LIMITS.improvements.min && i <= LIMITS.improvements.max;
        return {
            strengthsDone: strengthsDone,
            improvementsDone: improvementsDone,
            complete: strengthsDone && improvementsDone,
            strengthsText: `Select 3 strengths (${s} of 3)`,
            improvementsText: `Select 2 or 3 improvements (${i} selected)`
        };
    }

    function reason(kind, state) {
        if (state === 'taken') {
            return `Already picked as ${kind === 'strengths' ? 'an improvement' : 'a strength'}`;
        }
        if (state === 'full') {
            return `${LIMITS[kind].max} ${NOUN[kind]}s picked; deselect one to choose another`;
        }
        return '';
    }

    /**
     * Draw a picker and keep it in sync.
     *
     * @param {Object} options
     * @param {Array} options.tenets - [{id, name, description}]
     * @param {Element} options.strengthsEl - container for the strength buttons
     * @param {Element} options.improvementsEl - container for the improvement buttons
     * @param {Element} [options.checklistEl] - checklist holding [data-check=title|strengths|improvements]
     * @param {string} [options.completeTitle] - checklist title once the selection is valid
     * @param {Object} [options.selected] - initial {strengths, improvements}
     * @param {function} [options.onChange] - called with a copy of the selection after each click
     * @returns {{get: function, set: function}}
     */
    function create(options) {
        let selection = copy(options.selected || { strengths: [], improvements: [] });
        const containers = { strengths: options.strengthsEl, improvements: options.improvementsEl };

        function renderList(kind) {
            const el = containers[kind];
            el.setAttribute('role', 'group');
            if (!el.hasAttribute('aria-label') && !el.hasAttribute('aria-labelledby')) {
                el.setAttribute('aria-label', kind === 'strengths' ? 'Strengths' : 'Improvements');
            }
            el.innerHTML = '';
            options.tenets.forEach(tenet => {
                const state = availability(selection, kind, tenet.id);
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'tenet-item';
                if (state === 'selected') {
                    button.classList.add(kind === 'strengths' ? 'selected-strength' : 'selected-improvement');
                }
                if (state === 'taken' || state === 'full') {
                    button.classList.add('disabled');
                    button.setAttribute('aria-disabled', 'true');  // still focusable, so the reason is reachable
                    button.title = reason(kind, state);
                }
                button.setAttribute('aria-pressed', state === 'selected' ? 'true' : 'false');
                button.innerHTML = '<span class="tenet-name"></span><span class="tenet-description"></span>';
                button.querySelector('.tenet-name').textContent = tenet.name;
                button.querySelector('.tenet-description').textContent = tenet.description || '';
                button.addEventListener('click', () => click(kind, tenet.id));
                el.appendChild(button);
            });
        }

        function renderChecklist() {
            const el = options.checklistEl;
            if (!el) return;
            const st = status(selection);
            const part = name => el.querySelector(`[data-check="${name}"]`);
            part('strengths').textContent = st.strengthsText;
            part('strengths').classList.toggle('done', st.strengthsDone);
            part('improvements').textContent = st.improvementsText;
            part('improvements').classList.toggle('done', st.improvementsDone);
            el.classList.toggle('complete', st.complete);
            part('title').textContent = st.complete ? (options.completeTitle || '✓ Selection complete') : 'Selection progress:';
        }

        function render() {
            renderList('strengths');
            renderList('improvements');
            renderChecklist();
        }

        function click(kind, id) {
            const next = toggle(selection, kind, id);
            if (next[kind].length === selection[kind].length) return;  // not allowed: nothing changes
            selection = next;
            // Re-rendering replaces the buttons; keep keyboard focus on the one clicked
            const index = options.tenets.findIndex(t => t.id === id);
            render();
            containers[kind].children[index].focus();
            if (options.onChange) options.onChange(copy(selection));
        }

        render();
        return {
            get: () => copy(selection),
            set: value => { selection = copy(value); render(); }
        };
    }

    const api = { LIMITS: LIMITS, availability: availability, toggle: toggle, status: status, create: create };
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;  // Node (tests)
    } else {
        root.TenetPicker = api;
    }
})(this);
