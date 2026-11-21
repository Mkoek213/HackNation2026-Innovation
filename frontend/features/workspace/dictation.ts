"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { flushSync } from "react-dom";

const limit = 4000;

type SpeechAlternative = { readonly transcript: string };
type SpeechResult = ArrayLike<SpeechAlternative> & { readonly isFinal: boolean };
type SpeechResultEvent = { readonly results: ArrayLike<SpeechResult> };
type SpeechErrorEvent = { readonly error: string };

type BrowserSpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  processLocally?: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: ((event: SpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

export type DictationNotice = { text: string; tone: "listening" | "done" | "error" };

function speechConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const host = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  // The prefixed recognizer is the one that honors pl-PL. The unprefixed API can
  // fall back to an English on-device model when a Polish pack is not installed.
  return host.webkitSpeechRecognition ?? host.SpeechRecognition ?? null;
}

function spokenText(event: SpeechResultEvent) {
  let text = "";
  for (let index = 0; index < event.results.length; index += 1) text += event.results[index]?.[0]?.transcript ?? "";
  return text.replace(/\s+/g, " ").trim();
}

/** Spaces the dictated phrase from the text around it, so it never fuses with neighbouring words. */
function spaced(before: string, spoken: string, after: string) {
  if (!spoken) return "";
  const lead = before && !/[\s(„"]$/.test(before) ? " " : "";
  const trail = after && !/^[\s.,;:!?)”"]/.test(after) ? " " : "";
  return `${lead}${spoken}${trail}`;
}

/** Maps a caret offset across the replacement of [from, to) by text of the given length. */
function shift(offset: number, from: number, to: number, length: number) {
  if (offset >= to) return offset + length - (to - from);
  if (offset <= from) return offset;
  return from + length;
}

function failure(code: string) {
  if (code === "not-allowed" || code === "service-not-allowed") return "Brak dostępu do mikrofonu. Zezwól na mikrofon w przeglądarce i spróbuj ponownie.";
  if (code === "audio-capture") return "Nie znaleziono mikrofonu. Sprawdź urządzenie i spróbuj ponownie.";
  if (code === "network") return "Nie udało się rozpoznać mowy. Sprawdź połączenie i spróbuj ponownie.";
  if (code === "language-not-supported") return "Ta przeglądarka nie rozpoznaje języka polskiego.";
  return "Nie udało się włączyć mikrofonu. Spróbuj ponownie.";
}

/**
 * Browser dictation into a text field that the person can type into at the same time.
 * Each phrase is inserted at the caret (replacing a selection). Typing before or after the phrase
 * being recognized only moves it; editing inside it ends that phrase, and the next one starts at the caret.
 */
export function useDictation(field: RefObject<HTMLTextAreaElement | null>, write: (value: string) => void) {
  const [listening, setListening] = useState(false);
  const [notice, setNotice] = useState<DictationNotice | null>(null);
  const recognition = useRef<BrowserSpeechRecognition | null>(null);
  // The field text as last written or edited, and the span of it that holds the phrase being recognized.
  const text = useRef("");
  const slot = useRef({ from: 0, to: 0 });
  const want = useRef(false);
  const accept = useRef(false);
  const silent = useRef(false);
  const misses = useRef(0);
  const epoch = useRef(0);
  const mounted = useRef(true);
  const beginRef = useRef<(announce: boolean) => void>(() => {});

  const say = useCallback((text: string, tone: DictationNotice["tone"]) => {
    if (mounted.current) setNotice({ text, tone });
  }, []);

  // Drops the rest of the current phrase; while dictation is on, onend starts the next one at the caret.
  const restartPhrase = useCallback(() => {
    accept.current = false;
    recognition.current?.abort();
  }, []);

  const begin = useCallback((announce: boolean) => {
    const Ctor = speechConstructor();
    if (!Ctor) {
      want.current = false;
      say("Dyktowanie nie jest dostępne w tej przeglądarce. Wpisz wiadomość albo użyj Chrome, Edge lub Safari.", "error");
      return;
    }
    const element = field.current;
    const value = element?.value ?? "";
    const from = element?.selectionStart ?? value.length;
    const to = element?.selectionEnd ?? value.length;
    if (value.length - (to - from) >= limit) {
      want.current = false;
      if (mounted.current) setListening(false);
      say("Osiągnięto limit 4000 znaków. Skróć wiadomość, aby dyktować dalej.", "error");
      return;
    }
    const token = epoch.current;
    const session = new Ctor();
    recognition.current = session;
    // One phrase per start. Continuous mode makes Chrome keep the browser language,
    // which is often English, and ignore pl-PL. onend starts the next Polish phrase.
    session.continuous = false;
    session.interimResults = true;
    session.maxAlternatives = 1;
    if ("processLocally" in session) session.processLocally = false;
    session.lang = "pl-PL";
    text.current = value;
    slot.current = { from, to };
    accept.current = true;
    session.onresult = event => {
      if (!accept.current || epoch.current !== token) return;
      const element = field.current;
      if (!element) return;
      // The field changed without a reported edit: never overwrite it, continue at the caret instead.
      if (element.value !== text.current) {
        restartPhrase();
        return;
      }
      misses.current = 0;
      silent.current = false;
      const { from, to } = slot.current;
      const before = text.current.slice(0, from);
      const after = text.current.slice(to);
      const room = limit - before.length - after.length;
      let phrase = spaced(before, spokenText(event), after);
      const full = phrase.length >= room;
      if (full) phrase = phrase.slice(0, Math.max(room, 0));
      const next = `${before}${phrase}${after}`;
      // A caret on the phrase follows it; a caret the person placed elsewhere keeps its place in the text.
      const follows = element.selectionStart === from && element.selectionEnd === to;
      const start = follows ? from + phrase.length : shift(element.selectionStart, from, to, phrase.length);
      const end = follows ? start : shift(element.selectionEnd, from, to, phrase.length);
      text.current = next;
      slot.current = { from, to: from + phrase.length };
      flushSync(() => write(next));
      // Replacing the value moves the browser caret to the end; put it back.
      if (element.value === next) element.setSelectionRange(start, end);
      if (full) {
        want.current = false;
        accept.current = false;
        epoch.current += 1;
        session.stop();
        if (mounted.current) setListening(false);
        say("Osiągnięto limit 4000 znaków. Sprawdź tekst przed wysłaniem.", "done");
      }
    };
    session.onerror = event => {
      if (event.error === "aborted" || epoch.current !== token) return;
      if (event.error === "no-speech") {
        silent.current = true;
        return;
      }
      want.current = false;
      accept.current = false;
      silent.current = false;
      epoch.current += 1;
      if (mounted.current) setListening(false);
      say(failure(event.error), "error");
    };
    session.onend = () => {
      if (!mounted.current || epoch.current !== token) return;
      accept.current = false;
      if (want.current) {
        if (silent.current) {
          silent.current = false;
          misses.current += 1;
          if (misses.current >= 2) {
            want.current = false;
            setListening(false);
            say("Nie wykryto mowy. Kliknij mikrofon i spróbuj ponownie.", "error");
            return;
          }
        }
        window.setTimeout(() => {
          if (!want.current || !mounted.current || epoch.current !== token) return;
          beginRef.current(false);
        }, 200);
        return;
      }
      setListening(false);
      if (silent.current) {
        silent.current = false;
        say("Nie wykryto mowy. Kliknij mikrofon i spróbuj ponownie.", "error");
      }
    };
    try {
      session.lang = "pl-PL";
      session.start();
      if (mounted.current) setListening(true);
      if (announce) say("Słucham. Mów po polsku. Tekst pojawi się w miejscu kursora.", "listening");
    } catch {
      want.current = false;
      accept.current = false;
      epoch.current += 1;
      if (mounted.current) setListening(false);
      say("Nie udało się włączyć mikrofonu. Spróbuj ponownie.", "error");
    }
  }, [field, restartPhrase, say, write]);

  useEffect(() => {
    beginRef.current = begin;
  }, [begin]);

  /** Reports a manual change of the field, so dictation moves around it instead of overwriting it. */
  const edited = useCallback((next: string) => {
    const previous = text.current;
    text.current = next;
    if (!accept.current) return;
    let head = 0;
    const shortest = Math.min(previous.length, next.length);
    while (head < shortest && previous[head] === next[head]) head += 1;
    let tail = 0;
    while (tail < shortest - head && previous[previous.length - 1 - tail] === next[next.length - 1 - tail]) tail += 1;
    const { from, to } = slot.current;
    if (previous.length - tail <= from) {
      const delta = next.length - previous.length;
      slot.current = { from: from + delta, to: to + delta };
    } else if (head < to) restartPhrase();
  }, [restartPhrase]);

  const cancel = useCallback(() => {
    epoch.current += 1;
    want.current = false;
    accept.current = false;
    silent.current = false;
    misses.current = 0;
    recognition.current?.abort();
    recognition.current = null;
    if (mounted.current) {
      setListening(false);
      setNotice(null);
    }
  }, []);

  const stop = useCallback(() => {
    want.current = false;
    silent.current = false;
    recognition.current?.stop();
    setListening(false);
    say("Dyktowanie zakończone. Sprawdź tekst przed wysłaniem.", "done");
  }, [say]);

  const toggle = useCallback(() => {
    if (want.current) {
      stop();
      return;
    }
    if (!speechConstructor()) {
      say("Dyktowanie nie jest dostępne w tej przeglądarce. Wpisz wiadomość albo użyj Chrome, Edge lub Safari.", "error");
      return;
    }
    want.current = true;
    silent.current = false;
    misses.current = 0;
    begin(true);
  }, [begin, say, stop]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      epoch.current += 1;
      want.current = false;
      accept.current = false;
      recognition.current?.abort();
    };
  }, []);

  return { listening, notice, toggle, stop, edited, cancel };
}
