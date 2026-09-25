/**
 * Copy-for-Workday text: the single producer of the format that
 * WorkdayFeedback.parse_structured_feedback() (models.py) reads back when a
 * Workday export is imported. Human-readable sections come first and the
 * machine-readable [TENETS] block last.
 *
 * tests/test_workday_format.py runs this file under Node and parses its output
 * with the Python importer, so a format change that breaks import fails there.
 */
(function (root) {
    function bullets(ids, tenets) {
        return ids.map(id => {
            const tenet = tenets.find(t => t.id === id);
            return '• ' + (tenet ? tenet.name : id);
        }).join('\n');
    }

    function comment(text) {
        text = (text || '').trim();
        return text ? `\n${text}\n` : '';
    }

    function tenetsBlock(strengths, improvements) {
        return `\n[TENETS]\nStrengths: ${strengths.join(', ')}\nImprovements: ${improvements.join(', ')}\n[/TENETS]`;
    }

    /**
     * Peer feedback: each section carries its own comment.
     * @param {Array} tenets - [{id, name}] used to print tenet names
     * @param {Object} fb - {strengths, improvements, strengths_text, improvements_text}
     */
    function peer(tenets, fb) {
        return `Strengths:\n${bullets(fb.strengths, tenets)}\n` + comment(fb.strengths_text)
            + `\nAreas for Improvement:\n${bullets(fb.improvements, tenets)}\n` + comment(fb.improvements_text)
            + tenetsBlock(fb.strengths, fb.improvements);
    }

    /**
     * Manager feedback: one overall comment after both sections.
     * @param {Array} tenets - [{id, name}] used to print tenet names
     * @param {Object} fb - {strengths, improvements, feedback_text}
     */
    function manager(tenets, fb) {
        let text = `Strengths:\n${bullets(fb.strengths, tenets)}\n\n`
            + `Areas for Improvement:\n${bullets(fb.improvements, tenets)}\n`;
        const overall = (fb.feedback_text || '').trim();
        if (overall) {
            text += `\nManager's Feedback:\n${overall}\n`;
        }
        return text + tenetsBlock(fb.strengths, fb.improvements);
    }

    const api = { peer: peer, manager: manager };
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;  // Node (tests)
    } else {
        root.WorkdayFormat = api;
    }
})(this);
