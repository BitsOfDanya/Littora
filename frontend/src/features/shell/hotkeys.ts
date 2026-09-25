"use client";

import { useEffect, useRef } from "react";

export type HotkeyOptions = {
  shift?: boolean;
  mod?: boolean;
  alt?: boolean;
  enabled?: boolean;
  allowInInputs?: boolean;
  preventDefault?: boolean;
};

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

function matches(event: KeyboardEvent, code: string, options: HotkeyOptions): boolean {
  if (event.code !== code) return false;
  if (Boolean(options.shift) !== event.shiftKey) return false;
  if (Boolean(options.alt) !== event.altKey) return false;
  const modPressed = event.metaKey || event.ctrlKey;
  return Boolean(options.mod) === modPressed;
}

export function useHotkey(
  code: string | readonly string[],
  handler: (event: KeyboardEvent) => void,
  options: HotkeyOptions = {},
): void {
  const handlerRef = useRef(handler);
  const codes = Array.isArray(code) ? code : [code];
  const codesKey = codes.join("|");
  const { enabled = true, allowInInputs = false, preventDefault = true, shift, mod, alt } = options;

  useEffect(() => {
    handlerRef.current = handler;
  });

  useEffect(() => {
    if (!enabled) return;
    const keys = codesKey.split("|");
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.repeat && !keys.some((key) => key.startsWith("Bracket") || key.startsWith("Arrow")))
        return;
      if (!allowInInputs && isTypingTarget(event.target)) return;
      if (!keys.some((key) => matches(event, key, { shift, mod, alt }))) return;
      if (preventDefault) event.preventDefault();
      handlerRef.current(event);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [codesKey, enabled, allowInInputs, preventDefault, shift, mod, alt]);
}

export function useKeyAlias(
  key: string,
  handler: (event: KeyboardEvent) => void,
  { enabled = true }: Pick<HotkeyOptions, "enabled"> = {},
): void {
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  });

  useEffect(() => {
    if (!enabled) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || event.key !== key || event.altKey || event.ctrlKey || event.metaKey)
        return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      handlerRef.current(event);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [key, enabled]);
}
