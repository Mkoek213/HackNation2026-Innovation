"use client";

import { useSyncExternalStore } from "react";

const contrastKey = "radar-a11y-contrast";
const fontKey = "radar-a11y-font";
const fonts = ["100", "112", "125"] as const;
type FontScale = (typeof fonts)[number];

let contrastState = false;
let fontState: FontScale = "100";
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function apply(contrast: boolean, font: FontScale) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.contrast = contrast ? "high" : "default";
  root.style.setProperty("--font-scale", `${Number(font) / 100}`);
  root.style.fontSize = `${font}%`;
}

function readStored() {
  if (typeof window === "undefined") return;
  contrastState = window.localStorage.getItem(contrastKey) === "high";
  const value = window.localStorage.getItem(fontKey);
  fontState = fonts.includes(value as FontScale) ? (value as FontScale) : "100";
  apply(contrastState, fontState);
}

if (typeof window !== "undefined") readStored();

function setContrast(next: boolean) {
  contrastState = next;
  window.localStorage.setItem(contrastKey, next ? "high" : "default");
  apply(contrastState, fontState);
  emit();
}

function setFont(next: FontScale) {
  fontState = next;
  window.localStorage.setItem(fontKey, next);
  apply(contrastState, fontState);
  emit();
}

export function AccessibilityBar() {
  const contrast = useSyncExternalStore(subscribe, () => contrastState, () => false);
  const font = useSyncExternalStore(subscribe, () => fontState, () => "100" as FontScale);

  function bump(delta: -1 | 1) {
    const index = Math.min(fonts.length - 1, Math.max(0, fonts.indexOf(font) + delta));
    setFont(fonts[index]!);
  }

  return <div className="a11y-bar" role="region" aria-label="Ustawienia dostępności">
    <button type="button" className="a11y-btn" aria-pressed={contrast} onClick={() => setContrast(!contrast)}>
      Wysoki kontrast
    </button>
    <div className="a11y-font" role="group" aria-label="Rozmiar czcionki">
      <button type="button" className="a11y-btn" aria-label="Zmniejsz czcionkę" disabled={font === "100"} onClick={() => bump(-1)}>A−</button>
      <button type="button" className="a11y-btn" aria-label="Resetuj rozmiar czcionki" onClick={() => setFont("100")}>A</button>
      <button type="button" className="a11y-btn" aria-label="Powiększ czcionkę" disabled={font === "125"} onClick={() => bump(1)}>A+</button>
    </div>
  </div>;
}
