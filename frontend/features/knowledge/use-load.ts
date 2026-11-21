"use client";

import { useEffect, useState } from "react";

/** Load data for `key`; `null` while loading, `false` on failure. A new key starts a new load. */
export function useLoad<T>(load: () => Promise<T>, key: string | null) {
  const [state, setState] = useState<{ key: string | null; data: T | false }>({ key: null, data: false });
  useEffect(() => {
    if (key === null) return;
    let live = true;
    load().then(data => { if (live) setState({ key, data }); }).catch(() => { if (live) setState({ key, data: false }); });
    return () => { live = false; };
    // The key identifies the request; `load` is recreated on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state.key === key ? state.data : null;
}
