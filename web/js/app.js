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
            llm: 'claude-cli',
            llm_model: null,
            diarize: false,
            context: false,
            context_limit: 0,
            stream: false,
            conversation: false,
            input_device: null,
            compute: 'cpu',
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
                LiveScribeUI.appendResponseChunk(msg.id, msg.chunk);
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
                        response: 'Awaiting response\u2026',
                        pending: true,
                    });
                }
            });
        });

        // Save button — download transcript in the selected format
        document.getElementById('btn-save').addEventListener('click', function () {
            var fmt = document.getElementById('save-format').value;
            var a = document.createElement('a');
            a.href = '/api/transcript/export?format=' + encodeURIComponent(fmt);
            a.download = '';  // let the Content-Disposition header set the filename
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        });

        // Settings modal
        document.getElementById('btn-settings').addEventListener('click', function () {
            LiveScribeUI.applySettingsToForm(state.settings);
            // Fetch audio devices and populate dropdown each time modal opens
            fetch('/api/devices')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var select = document.getElementById('setting-input-device');
                    var currentVal = select.value;
                    select.innerHTML = '<option value="">System Default</option>';
                    (data.devices || []).forEach(function (dev) {
                        var opt = document.createElement('option');
                        opt.value = dev.index;
                        opt.textContent = dev.name + ' (ch: ' + dev.channels + ')' + (dev.default ? ' [default]' : '');
                        select.appendChild(opt);
                    });
                    // Restore selection
                    if (state.settings.input_device != null) {
                        select.value = state.settings.input_device;
                    } else {
                        select.value = '';
                    }
                })
                .catch(function (err) {
                    console.error('Failed to fetch audio devices:', err);
                });
            LiveScribeUI.showSettingsModal();
        });

        document.getElementById('btn-close-settings').addEventListener('click', function () {
            LiveScribeUI.hideSettingsModal();
        });

        document.querySelector('.modal__backdrop').addEventListener('click', function () {
            LiveScribeUI.hideSettingsModal();
        });

        // Preset dropdown change
        document.getElementById('setting-preset').addEventListener('change', function () {
            LiveScribeUI.onPresetChange();
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

        // Context checkbox toggles context-limit visibility
        document.getElementById('setting-context').addEventListener('change', function () {
            LiveScribeUI.toggleContextLimit();
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

    // --- Load presets from server ---
    function loadPresets() {
        fetch('/api/presets')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                LiveScribeUI.populatePresets(data.presets, data.default);
                // Sync preset dropdown to current prompt
                LiveScribeUI.syncPresetSelect(state.settings.prompt);
            })
            .catch(function (err) {
                console.error('[App] Failed to load presets:', err);
            });
    }

    // --- Init ---
    function init() {
        connectWebSocket();
        bindEventListeners();
        loadSettings();
        loadPresets();
    }

    // Wait for DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
