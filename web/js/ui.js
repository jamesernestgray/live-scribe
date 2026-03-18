/**
 * ui.js — DOM updates, event handlers, speaker color management.
 */

var LiveScribeUI = (function () {
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

        var div = document.createElement('div');
        div.className = 'response';

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
        return {
            model: document.getElementById('setting-model').value,
            language: document.getElementById('setting-language').value || null,
            interval: parseInt(document.getElementById('setting-interval').value, 10) || 60,
            prompt: document.getElementById('setting-prompt').value,
            llm_model: document.getElementById('setting-llm-model').value || null,
        };
    }

    function applySettingsToForm(settings) {
        if (settings.model) document.getElementById('setting-model').value = settings.model;
        if (settings.language) document.getElementById('setting-language').value = settings.language;
        if (settings.interval) document.getElementById('setting-interval').value = settings.interval;
        if (settings.prompt) document.getElementById('setting-prompt').value = settings.prompt;
        if (settings.llm_model) document.getElementById('setting-llm-model').value = settings.llm_model;
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

    return {
        addSegment: addSegment,
        addResponse: addResponse,
        updateStatus: updateStatus,
        setConnected: setConnected,
        showSettingsModal: showSettingsModal,
        hideSettingsModal: hideSettingsModal,
        getSettingsFromForm: getSettingsFromForm,
        applySettingsToForm: applySettingsToForm,
        setTheme: setTheme,
        clearTranscript: clearTranscript,
    };
})();
