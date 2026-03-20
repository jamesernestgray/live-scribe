/**
 * ui.js — DOM updates, event handlers, speaker color management.
 */

var LiveScribeUI = (function () {
    // Preset data (populated by loadPresets)
    var _presets = {};
    var _defaultPreset = 'collaborator';

    // Speaker color assignment
    var _speakerColors = {};
    var _speakerCount = 0;
    var _maxColors = 6;

    function getSpeakerColor(speaker) {
        if (!speaker) return null;
        if (_speakerColors[speaker] !== undefined) {
            return _speakerColors[speaker];
        }
        var idx = _speakerCount % _maxColors;
        _speakerColors[speaker] = idx;
        _speakerCount++;
        return idx;
    }

    // Auto-scroll tracking
    var _autoScroll = true;

    function _checkAutoScroll(container) {
        // Auto-scroll if user is near the bottom
        var threshold = 60;
        return (container.scrollTop + container.clientHeight + threshold >= container.scrollHeight);
    }

    // --- DOM updates ---

    function addSegment(segment) {
        var container = document.getElementById('transcript');
        var emptyState = container.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        var shouldScroll = _checkAutoScroll(container);

        var div = document.createElement('div');
        div.className = 'segment';

        var meta = document.createElement('div');
        meta.className = 'segment__meta';

        var timeSpan = document.createElement('span');
        timeSpan.className = 'segment__time';
        timeSpan.textContent = segment.time || '';
        meta.appendChild(timeSpan);

        if (segment.speaker) {
            var speakerSpan = document.createElement('span');
            speakerSpan.className = 'segment__speaker';
            var colorIdx = getSpeakerColor(segment.speaker);
            speakerSpan.style.setProperty('--speaker-color', 'var(--speaker-' + colorIdx + ')');
            speakerSpan.textContent = segment.speaker;
            meta.appendChild(speakerSpan);
        }

        div.appendChild(meta);

        var text = document.createElement('div');
        text.className = 'segment__text';
        text.textContent = segment.text || '';
        div.appendChild(text);

        container.appendChild(div);

        if (shouldScroll) {
            container.scrollTop = container.scrollHeight;
        }

        // Update segment count
        var countEl = document.getElementById('segment-count');
        var count = container.querySelectorAll('.segment').length;
        countEl.textContent = count + ' segment' + (count !== 1 ? 's' : '');
    }

    function addResponse(response) {
        var container = document.getElementById('responses');
        var emptyState = container.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        // If a placeholder for this dispatch ID already exists, update it
        var existing = response.id ? container.querySelector('[data-dispatch-id="' + response.id + '"]') : null;
        if (existing) {
            existing.querySelector('.response__time').textContent = response.time || '';
            existing.querySelector('.response__text').textContent = response.response || '';
            existing.classList.remove('response--pending');
            container.scrollTop = container.scrollHeight;
            return;
        }

        var div = document.createElement('div');
        div.className = 'response';
        if (response.id) div.dataset.dispatchId = response.id;

        var header = document.createElement('div');
        header.className = 'response__header';

        var idSpan = document.createElement('span');
        idSpan.className = 'response__id';
        idSpan.textContent = 'Dispatch #' + (response.id || '?');
        header.appendChild(idSpan);

        var timeSpan = document.createElement('span');
        timeSpan.className = 'response__time';
        timeSpan.textContent = response.time || '';
        header.appendChild(timeSpan);

        div.appendChild(header);

        var text = document.createElement('div');
        text.className = 'response__text';
        text.textContent = response.response || '';
        div.appendChild(text);

        // Mark as pending if it's a placeholder
        if (response.pending) {
            div.classList.add('response--pending');
        }

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;

        // Update count
        var countEl = document.getElementById('response-count');
        var count = container.querySelectorAll('.response').length;
        countEl.textContent = count;
    }

    function updateStatus(status) {
        var dot = document.getElementById('status-indicator');
        var statusText = document.getElementById('status-text');
        var toggleBtn = document.getElementById('btn-toggle');
        var dispatchBtn = document.getElementById('btn-dispatch');
        var saveBtn = document.getElementById('btn-save');
        var saveFormat = document.getElementById('save-format');

        if (status.recording) {
            dot.className = 'status-dot status-dot--active';
            statusText.textContent = 'Recording \u2014 ' + (status.segments || 0) + ' segments \u2014 model: ' + (status.model || '?');
            toggleBtn.dataset.state = 'recording';
            toggleBtn.querySelector('.btn__icon').innerHTML = '&#9632;';
            toggleBtn.querySelector('.btn__label').textContent = 'Stop';
            toggleBtn.classList.remove('btn--primary');
            toggleBtn.classList.add('btn--danger');
            dispatchBtn.disabled = false;
            saveBtn.disabled = false;
            if (saveFormat) saveFormat.disabled = false;
        } else {
            dot.className = 'status-dot status-dot--inactive';
            statusText.textContent = 'Idle' + (status.segments ? ' \u2014 ' + status.segments + ' segments' : '');
            toggleBtn.dataset.state = 'stopped';
            toggleBtn.querySelector('.btn__icon').innerHTML = '&#9654;';
            toggleBtn.querySelector('.btn__label').textContent = 'Start';
            toggleBtn.classList.remove('btn--danger');
            toggleBtn.classList.add('btn--primary');
            dispatchBtn.disabled = true;
        }
    }

    function setConnected(connected) {
        var statusText = document.getElementById('status-text');
        if (!connected) {
            statusText.textContent = 'Disconnected \u2014 reconnecting...';
        }
    }

    function showSettingsModal() {
        document.getElementById('settings-modal').hidden = false;
    }

    function hideSettingsModal() {
        document.getElementById('settings-modal').hidden = true;
    }

    function getSettingsFromForm() {
        var inputDeviceVal = document.getElementById('setting-input-device').value;
        return {
            model: document.getElementById('setting-model').value,
            language: document.getElementById('setting-language').value || null,
            interval: parseInt(document.getElementById('setting-interval').value, 10) || 60,
            prompt: document.getElementById('setting-prompt').value,
            llm: document.getElementById('setting-llm').value,
            llm_model: document.getElementById('setting-llm-model').value || null,
            diarize: document.getElementById('setting-diarize').checked,
            context: document.getElementById('setting-context').checked,
            context_limit: parseInt(document.getElementById('setting-context-limit').value, 10) || 0,
            stream: document.getElementById('setting-stream').checked,
            conversation: document.getElementById('setting-conversation').checked,
            input_device: inputDeviceVal === '' ? null : parseInt(inputDeviceVal, 10),
            compute: document.getElementById('setting-compute').value,
        };
    }

    function applySettingsToForm(settings) {
        if (settings.model) document.getElementById('setting-model').value = settings.model;
        if (settings.language) document.getElementById('setting-language').value = settings.language;
        if (settings.interval) document.getElementById('setting-interval').value = settings.interval;
        if (settings.prompt) document.getElementById('setting-prompt').value = settings.prompt;
        if (settings.llm) document.getElementById('setting-llm').value = settings.llm;
        if (settings.llm_model) document.getElementById('setting-llm-model').value = settings.llm_model;
        document.getElementById('setting-diarize').checked = !!settings.diarize;
        document.getElementById('setting-context').checked = !!settings.context;
        document.getElementById('setting-context-limit').value = settings.context_limit || 0;
        document.getElementById('setting-stream').checked = !!settings.stream;
        document.getElementById('setting-conversation').checked = !!settings.conversation;
        document.getElementById('setting-input-device').value = settings.input_device != null ? settings.input_device : '';
        if (settings.compute) document.getElementById('setting-compute').value = settings.compute;
        // Sync preset dropdown to match current prompt text
        if (settings.prompt) syncPresetSelect(settings.prompt);
        _toggleContextLimit();
    }

    function _toggleContextLimit() {
        var show = document.getElementById('setting-context').checked;
        document.getElementById('context-limit-group').hidden = !show;
    }

    function setTheme(theme) {
        document.documentElement.dataset.theme = theme;
        document.getElementById('setting-theme').value = theme;
    }

    function clearTranscript() {
        var container = document.getElementById('transcript');
        container.innerHTML = '<div class="empty-state">Press Start to begin transcription</div>';
        document.getElementById('segment-count').textContent = '0 segments';
    }

    function appendResponseChunk(id, chunk) {
        var container = document.getElementById('responses');
        var card = id ? container.querySelector('[data-dispatch-id="' + id + '"]') : null;

        if (!card) {
            // Create a new streaming card if one doesn't exist yet
            addResponse({
                id: id,
                time: new Date().toLocaleTimeString('en-GB', { hour12: false }),
                response: chunk,
                pending: true,
            });
            return;
        }

        var textEl = card.querySelector('.response__text');
        if (!textEl) return;

        // If the card still shows the placeholder text, replace it
        if (card.classList.contains('response--pending')) {
            textEl.textContent = chunk;
            card.classList.remove('response--pending');
        } else {
            textEl.textContent += chunk;
        }

        container.scrollTop = container.scrollHeight;
    }

    // --- Preset management ---

    function populatePresets(presets, defaultPreset) {
        _presets = presets || {};
        _defaultPreset = defaultPreset || 'collaborator';

        var select = document.getElementById('setting-preset');
        // Remove all options except "Custom"
        while (select.options.length > 0) {
            select.remove(0);
        }

        // Add preset options
        var names = Object.keys(_presets);
        for (var i = 0; i < names.length; i++) {
            var opt = document.createElement('option');
            opt.value = names[i];
            opt.textContent = names[i];
            select.appendChild(opt);
        }

        // Add "Custom" option last
        var customOpt = document.createElement('option');
        customOpt.value = 'custom';
        customOpt.textContent = 'Custom';
        select.appendChild(customOpt);
    }

    function onPresetChange() {
        var select = document.getElementById('setting-preset');
        var textarea = document.getElementById('setting-prompt');
        var presetName = select.value;

        if (presetName === 'custom') {
            textarea.readOnly = false;
        } else if (_presets[presetName]) {
            textarea.value = _presets[presetName];
            textarea.readOnly = true;
        }
    }

    function syncPresetSelect(promptText) {
        var select = document.getElementById('setting-preset');
        // Try to find a matching preset
        var names = Object.keys(_presets);
        for (var i = 0; i < names.length; i++) {
            if (_presets[names[i]] === promptText) {
                select.value = names[i];
                document.getElementById('setting-prompt').readOnly = true;
                return;
            }
        }
        // No match found — set to custom
        select.value = 'custom';
        document.getElementById('setting-prompt').readOnly = false;
    }

    function getPresets() {
        return _presets;
    }

    return {
        addSegment: addSegment,
        addResponse: addResponse,
        appendResponseChunk: appendResponseChunk,
        updateStatus: updateStatus,
        setConnected: setConnected,
        showSettingsModal: showSettingsModal,
        hideSettingsModal: hideSettingsModal,
        getSettingsFromForm: getSettingsFromForm,
        applySettingsToForm: applySettingsToForm,
        setTheme: setTheme,
        clearTranscript: clearTranscript,
        toggleContextLimit: _toggleContextLimit,
        populatePresets: populatePresets,
        onPresetChange: onPresetChange,
        syncPresetSelect: syncPresetSelect,
        getPresets: getPresets,
    };
})();
