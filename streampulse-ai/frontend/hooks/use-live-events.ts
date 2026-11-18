"use client";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

const INVALIDATE: Record<string, string[][]> = {
  "stream.updated": [["streams"], ["analytics"]],
  "capture.updated": [["streams"], ["stream"]],
  "activity": [["activity"], ["streams"]],
  "candidate.created": [["analytics"]],
  "candidate.evaluated": [["analytics"]],
  "clip.updated": [["clips"], ["clip"], ["analytics"]],
  "clip.deleted": [["clips"], ["analytics"]],
  "publish.updated": [["jobs"], ["clips"], ["clip"], ["analytics"]],
  "notification": [["notifications"]],
};

function wsUrl(): string {
  const env = process.env.NEXT_PUBLIC_WS_URL;
  if (env) return env;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.hostname}:8000/api/ws`;
}

/** Subscribes to backend events over WebSocket and refreshes affected queries. Reconnects with backoff. */
export function useLiveEvents(enabled: boolean) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let retry = 1000;
    let closed = false;
    let ping: ReturnType<typeof setInterval>;
    let timer: ReturnType<typeof setTimeout>;
    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        setConnected(true);
        retry = 1000;
        ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 25000);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as { type: string };
          for (const key of INVALIDATE[msg.type] || []) qc.invalidateQueries({ queryKey: key });
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        clearInterval(ping);
        if (!closed) timer = setTimeout(connect, (retry = Math.min(retry * 2, 30000)));
      };
    };
    connect();
    return () => {
      closed = true;
      clearInterval(ping);
      clearTimeout(timer);
      ws?.close();
    };
  }, [enabled, qc]);
  return connected;
}
