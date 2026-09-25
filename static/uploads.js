/**
 * File uploads shared by the home, individual and dashboard pages: the drop
 * zone behavior (click, keyboard, drag and drop) and the orgchart import.
 * Messages use plural() and escapeHtml() from base.html's script.
 */
(function (root) {
    /**
     * Make a .drop-zone open its file input on click, Enter or Space, and
     * accept a dropped file. A dropped file of the wrong type is reported in
     * statusEl instead of being ignored.
     *
     * @param {Element} zone - the .drop-zone element
     * @param {Element} input - its hidden <input type="file">
     * @param {Object} options - {extension: '.csv', statusEl, onFile(file)}
     */
    function dropZone(zone, input, options) {
        zone.tabIndex = 0;
        zone.setAttribute('role', 'button');

        zone.addEventListener('click', () => input.click());
        zone.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                input.click();
            }
        });

        input.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                options.onFile(e.target.files[0]);
            }
            input.value = '';  // choosing the same file again fires change again
        });

        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('drag-over');
        });
        zone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            zone.classList.remove('drag-over');
        });
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('drag-over');
            const files = Array.from(e.dataTransfer.files);
            const file = files.find(f => f.name.toLowerCase().endsWith(options.extension));
            if (file) {
                options.onFile(file);
            } else if (files.length > 0) {
                options.statusEl.innerHTML =
                    `<div class="error-message">Drop a ${options.extension} file: ` +
                    `${escapeHtml(files[0].name)} is not one.</div>`;
            }
        });
    }

    /**
     * Upload an orgchart CSV, report the result in statusEl and reload the
     * page on success so it shows the imported people.
     *
     * @param {string} url - the import endpoint (url_for('import_orgchart_web'))
     * @param {File} file
     * @param {boolean} reset - delete all existing data first
     * @param {Element} statusEl
     * @returns {Promise<boolean>} whether the import succeeded
     */
    function importOrgchart(url, file, reset, statusEl) {
        statusEl.innerHTML = '<p>Importing...</p>';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('reset', reset.toString());

        return fetch(url, { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (!data.success) {
                    throw new Error(data.error || 'Import failed');
                }
                let message = `Imported ${plural(data.new_count, 'new person', 'new people')}`;
                if (data.reset) {
                    message = `Database reset. Imported ${plural(data.new_count, 'person', 'people')}`;
                } else if (data.updated_count > 0) {
                    message += `, updated ${data.updated_count} existing`;
                }
                statusEl.innerHTML = `<div class="success-message">${message}. Reloading...</div>`;
                setTimeout(() => window.location.reload(), 1000);
                return true;
            })
            .catch(err => {
                statusEl.innerHTML = `<div class="error-message">Error: ${escapeHtml(err.message)}</div>`;
                return false;
            });
    }

    root.Uploads = { dropZone: dropZone, importOrgchart: importOrgchart };
})(this);
