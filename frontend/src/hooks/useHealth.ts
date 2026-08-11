//hook for getting service uptime health for display on UI

import { useEffect, useState } from "react";
import { api } from "../api/client";

//call get route and ensure a response. assuming it hits, we're connected.
export function useHealth(): { connected: boolean } {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    api.GET("/health").then(({ data }) => {
      setConnected(data != null);
    }).catch(() => {
      setConnected(false); //catch as a bad cx state otherwise
    });
  }, []);

  return { connected };
}
