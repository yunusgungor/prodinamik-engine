/**
 * WebSocket bağlantı hook'u — gerçek zamanlı engine iletişimi.
 * 
 * Kanallar:
 * - ws/runs/{slug}  → Run state değişimleri
 * - ws/human         → HITL soruları, approval bildirimleri
 * - ws/metrics       → Health score, degradation, alerts live stream
 * - ws/events        → Tüm engine event'leri (broadcast)
 */

import { useEffect, useRef, useState, useCallback } from "react";

type WSChannel = "runs" | "human" | "metrics" | "events";

interface WSOptions {
  channel: WSChannel;
  slug?: string;
  token?: string;
  onMessage?: (data: Record<string, unknown>) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  enabled?: boolean;
}

interface WSStatus {
  connected: boolean;
  lastPing: number | null;
  error: string | null;
}

export function useWebSocket({
  channel,
  slug,
  token,
  onMessage,
  onConnect,
  onDisconnect,
  enabled = true,
}: WSOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const pingTimer = useRef<ReturnType<typeof setInterval>>();
  const [status, setStatus] = useState<WSStatus>({
    connected: false,
    lastPing: null,
    error: null,
  });

  const getUrl = useCallback(() => {
    const base = localStorage.getItem("pdmk-auth")
      ? JSON.parse(localStorage.getItem("pdmk-auth") || "{}")?.state?.baseUrl
      : "http://localhost:8000";
    const wsBase = (base || "http://localhost:8000").replace(/^http/, "ws");
    const t = token || 
      (localStorage.getItem("pdmk-auth")
        ? JSON.parse(localStorage.getItem("pdmk-auth") || "{}")?.state?.apiKey
        : null);
    
    let path = `/ws/${channel}`;
    if (slug) path += `/${slug}`;
    if (t) path += `?token=${t}`;
    
    return `${wsBase}${path}`;
  }, [channel, slug, token]);

  const connect = useCallback(() => {
    if (!enabled) return;
    
    try {
      const url = getUrl();
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus({ connected: true, lastPing: null, error: null });
        onConnect?.();

        // Start ping interval
        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "pong") {
            setStatus((s) => ({ ...s, lastPing: Date.now() }));
            return;
          }
          onMessage?.(data);
        } catch {
          // Not JSON, ignore
        }
      };

      ws.onclose = () => {
        setStatus({ connected: false, lastPing: null, error: null });
        onDisconnect?.();
        wsRef.current = null;
        if (pingTimer.current) clearInterval(pingTimer.current);

        // Reconnect after 3s
        reconnectTimer.current = setTimeout(() => {
          connect();
        }, 3000);
      };

      ws.onerror = () => {
        setStatus((s) => ({ ...s, error: "WebSocket error" }));
      };
    } catch (e) {
      setStatus((s) => ({ ...s, error: String(e) }));
    }
  }, [enabled, getUrl, onConnect, onDisconnect, onMessage]);

  useEffect(() => {
    if (enabled) {
      connect();
    }

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (pingTimer.current) clearInterval(pingTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [enabled, connect]);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { ...status, send };
}

/**
 * Engine bağlantı durumu hook'u.
 * WebSocket + REST health check kombinasyonu.
 */
export function useEngineConnection() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);

  const check = useCallback(async () => {
    try {
      const base = localStorage.getItem("pdmk-auth")
        ? JSON.parse(localStorage.getItem("pdmk-auth") || "{}")?.state?.baseUrl
        : "http://localhost:8000";
      const res = await fetch(`${base || "http://localhost:8000"}/api/v1/healthz`);
      if (res.ok) {
        const data = await res.json();
        setConnected(data.status === "ok");
      } else {
        setConnected(false);
      }
    } catch {
      setConnected(false);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, [check]);

  return { connected, checking, healthCheck: check };
}
