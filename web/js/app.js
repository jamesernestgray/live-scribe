/**
 * app.js — Main init, state management, event binding for live-scribe Web UI.
 */

(function () {
    'use strict';

    var state = {
        recording: false,
        segments: [],
        responses: [],
        settings: {
            model: 'base',
            language: null,
            prompt: 'You are a real-time AI collaborator listening to a live audio transcription. '
                + 'Engage with what\'s being said: answer questions, provide analysis, '
                + 'offer relevant expertise, and surface useful context. '
                + 'If the speaker asks something, answer it directly. '
                + 'If they\'re discussing a design or problem, contribute meaningfully. '
                + 'Be concise and direct.',
            interval: 60,
            llm_model: null,
        },
    };

    // --- WebSocket URL ---
    function getWsUrl() {
        var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        return protocol + '//' + location.host + '/ws';
    }

    // --- API helpers ---
    function apiPost(path, body) {
        return fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : '{}',
        }).then(function (r) { return r.json(); });
    }

    // --- WebSocket message handler ---
    function onWsMessage(msg) {
        switch (msg.type) {
            case 'segment':
                state.segments.push(msg);
                LiveScribeUI.addSegment(msg);
                break;

            case 'llm_response':
                state.responses.push(msg);
                LiveScribeUI.addResponse(msg);
                break;

            case 'llm_streaming_chunk':
                // Future: handle streaming
                break;

            case 'status':
                state.recording = msg.recording;
                LiveScribeUI.updateStatus(msg);
                break;

            default:
                console.log('[App] Unknown message type:', msg.type);
        }
    }

    // --- Connect WebSocket ---
    function connectWebSocket() {
        LiveScribeWS.connect(getWsUrl(), {
            onMessage: onWsMessage,
            onOpen: function () {
                LiveScribeUI.setConnected(true);
            },
            onClose: function () {
                LiveScribeUI.setConnected(false);
            },
        });
    }

    // --- Reusable actions ---
    function toggleRecording() {
        if (state.recording) {
            apiPost('/api/stop').then(function (data) {
                if (data.error) console.error('Stop error:', data.error);
            });
        } else {
            LiveScribeUI.clearTranscript();
            state.segments = [];
            apiPost('/api/start', { config: state.settings }).then(function (data) {
                if (data.error) console.error('Start error:', data.error);
            });
        }
    }

    function dispatch() {
        var btn = document.getElementById('btn-dispatch');
        if (btn.disabled) return;
        apiPost('/api/dispatch').then(function (data) {
            if (data.ok) {
                LiveScribeUI.addResponse({
                    id: data.dispatch_id,
                    time: new Date().toLocaleTimeString('en-GB', { hour12: false }),
                    response: '(Dispatched to LLM \u2014 awaiting response...)',
                });
            }
        });
    }

    // --- Event listeners ---
    function bindEventListeners() {
        // Start/Stop toggle
        document.getElementById('btn-toggle').addEventListener('click', toggleRecording);

        // Dispatch button
        document.getElementById('btn-dispatch').addEventListener('click', function () {
            apiPost('/api/dispatch').then(function (data) {
                if (data.ok) {
                    LiveScribeUI.addResponse({
                        id: data.dispatch_id,
                        time: new Date().toLocaleTimeString('en-GB', { hour12: false }),
                        response: '(Dispatched to LLM \u2014 awaiting response...)',
                    });
                }
            });
        });

        // Save button
        document.getElementById('btn-save').addEventListener('click', function () {
            fetch('/api/transcript')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var lines = data.segments.map(function (s) {
                        var spk = s.speaker ? ' [' + s.speaker + ']' : '';
                        return '[' + s.time + ']' + spk + ' ' + s.text;
                    });
                    var blob = new Blob([lines.join('\n')], { type: 'text/plain' });
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement('a');
                    a.href = url;
                    a.download = 'transcript-' + new Date().toISOString().slice(0, 19).replace(/:/g, '-') + '.txt';
                    a.click();
                    URL.revokeObjectURL(url);
                });
        });

        // Settings modal
        document.getElementById('btn-settings').addEventListener('click', function () {
            LiveScribeUI.applySettingsToForm(state.settings);
            LiveScribeUI.showSettingsModal();
        });

        document.getElementById('btn-close-settings').addEventListener('click', function () {
            LiveScribeUI.hideSettingsModal();
        });

        document.querySelector('.modal__backdrop').addEventListener('click', function () {
            LiveScribeUI.hideSettingsModal();
        });

        document.getElementById('btn-save-settings').addEventListener('click', function () {
            var formSettings = LiveScribeUI.getSettingsFromForm();
            Object.assign(state.settings, formSettings);

            // Send to server
            apiPost('/api/settings', state.settings);

            // Apply theme locally
            var theme = document.getElementById('setting-theme').value;
            LiveScribeUI.setTheme(theme);

            // Persist settings to localStorage
            saveSettings();
            try { localStorage.setItem('live-scribe-theme', theme); } catch (e) { /* noop */ }

            LiveScribeUI.hideSettingsModal();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                LiveScribeUI.hideSettingsModal();
            }
            // Ctrl/Cmd + Enter = dispatch
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                dispatch();
            }
            // Ctrl/Cmd + Shift + R = toggle recording
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'R') {
                e.preventDefault();
                toggleRecording();
            }
        });
    }

    // --- Settings persistence ---
    function saveSettings() {
        try {
            localStorage.setItem('livescribe_settings', JSON.stringify(state.settings));
        } catch (e) { /* noop */ }
    }

    function loadSettings() {
        // Restore all settings
        try {
            var saved = localStorage.getItem('livescribe_settings');
            if (saved) {
                Object.assign(state.settings, JSON.parse(saved));
                LiveScribeUI.applySettingsToForm(state.settings);
            }
        } catch (e) { /* noop */ }

        // Theme (backward-compatible with existing key)
        try {
            var savedTheme = localStorage.getItem('live-scribe-theme');
            if (savedTheme) {
                LiveScribeUI.setTheme(savedTheme);
            }
        } catch (e) { /* noop */ }
    }

    // --- Init ---
    function init() {
        connectWebSocket();
        bindEventListeners();
        loadSettings();
    }

    // Wait for DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
