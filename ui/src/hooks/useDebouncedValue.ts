import { useEffect, useState } from "react";

/** Let text entry settle before querying the local service. */
export function useDebouncedValue(value: string, delay = 200): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return settled;
}
