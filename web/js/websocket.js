/**
 * websocket.js — WebSocket connection with auto-reconnect for live-scribe.
 */

const LiveScribeWS = (function () {
    let _ws = null;
    let _url = null;
    let _reconnectTimer = null;
    let _reconnectDelay = 1000;
    const _maxReconnectDelay = 30000;
    let _intentionallyClosed = false;
    let _onMessage = null;
    let _onOpen = null;
    let _onClose = null;

    function connect(url, callbacks) {
        _url = url;
        _onMessage = callbacks.onMessage || null;
        _onOpen = callbacks.onOpen || null;
        _onClose = callbacks.onClose || null;
        _intentionallyClosed = false;
        _open();
    }

    function _open() {
        if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) {
            return;
        }

        try {
            _ws = new WebSocket(_url);
        } catch (e) {
            console.error('[WS] Failed to create WebSocket:', e);
            _scheduleReconnect();
            return;
        }

        _ws.onopen = function () {
            console.log('[WS] Connected');
            _reconnectDelay = 1000;
            if (_onOpen) _onOpen();
        };

        _ws.onmessage = function (event) {
            try {
                var msg = JSON.parse(event.data);
                if (_onMessage) _onMessage(msg);
            } catch (e) {
                console.warn('[WS] Bad message:', event.data);
            }
        };

        _ws.onclose = function (event) {
            console.log('[WS] Closed:', event.code, event.reason);
            if (_onClose) _onClose();
            if (!_intentionallyClosed) {
                _scheduleReconnect();
            }
        };

        _ws.onerror = function (event) {
            console.error('[WS] Error:', event);
            // onclose will fire after this
        };
    }

    function _scheduleReconnect() {
        if (_reconnectTimer) return;
        console.log('[WS] Reconnecting in ' + _reconnectDelay + 'ms...');
        _reconnectTimer = setTimeout(function () {
            _reconnectTimer = null;
            _open();
            // Exponential backoff
            _reconnectDelay = Math.min(_reconnectDelay * 2, _maxReconnectDelay);
        }, _reconnectDelay);
    }

    function send(msg) {
        if (_ws && _ws.readyState === WebSocket.OPEN) {
            _ws.send(JSON.stringify(msg));
        } else {
            console.warn('[WS] Not connected, cannot send:', msg);
        }
    }

    function close() {
        _intentionallyClosed = true;
        if (_reconnectTimer) {
            clearTimeout(_reconnectTimer);
            _reconnectTimer = null;
        }
        if (_ws) {
            _ws.close();
        }
    }

    function isConnected() {
        return _ws && _ws.readyState === WebSocket.OPEN;
    }

    return {
        connect: connect,
        send: send,
        close: close,
        isConnected: isConnected,
    };
})();
