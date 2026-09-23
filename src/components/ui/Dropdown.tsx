"use client";

import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export type DropdownOption<T extends string | number> = {
  value: T;
  label: string;
};

type DropdownProps<T extends string | number> = {
  value: T | null;
  options: readonly DropdownOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  fallbackLabel?: string;
  className?: string;
  align?: "start" | "end";
};

function ChevronIcon() {
  return (
    <svg className="ui-dropdown-chevron" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <path
        d="M1.5 3.5 5 7l3.5-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="ui-dropdown-check" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <path
        d="M1.5 5.2 3.9 7.5 8.5 2.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Dropdown<T extends string | number>({
  value,
  options,
  onChange,
  ariaLabel,
  fallbackLabel,
  className,
  align = "start",
}: DropdownProps<T>) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const selectedIndex = options.findIndex((option) => option.value === value);
  const selectedLabel = selectedIndex >= 0 ? options[selectedIndex].label : (fallbackLabel ?? "");

  const closeMenu = useCallback(() => {
    setOpen(false);
    setActiveIndex(-1);
  }, []);

  const openMenu = useCallback(() => {
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  }, [selectedIndex]);

  const commit = useCallback(
    (index: number) => {
      const option = options[index];
      if (option) onChange(option.value);
      closeMenu();
      triggerRef.current?.focus();
    },
    [closeMenu, onChange, options],
  );

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: globalThis.PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) closeMenu();
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open, closeMenu]);

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    listRef.current?.children[activeIndex]?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowDown":
      case "ArrowUp": {
        event.preventDefault();
        if (!open) {
          openMenu();
          return;
        }
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActiveIndex((current) => {
          const next = current + step;
          if (next < 0) return options.length - 1;
          if (next >= options.length) return 0;
          return next;
        });
        return;
      }
      case "Home":
        if (open) {
          event.preventDefault();
          setActiveIndex(0);
        }
        return;
      case "End":
        if (open) {
          event.preventDefault();
          setActiveIndex(options.length - 1);
        }
        return;
      case "Enter":
      case " ":
        event.preventDefault();
        if (open) commit(activeIndex);
        else openMenu();
        return;
      case "Escape":
        if (open) {
          event.preventDefault();
          event.stopPropagation();
          closeMenu();
          triggerRef.current?.blur();
        }
        return;
      case "Tab":
        closeMenu();
        return;
      default:
    }
  };

  return (
    <div
      ref={rootRef}
      className={className ? `ui-dropdown ${className}` : "ui-dropdown"}
      data-open={open ? "true" : "false"}
      data-align={align}
      onKeyDown={handleKeyDown}
    >
      <button
        ref={triggerRef}
        type="button"
        className="ui-dropdown-trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
        onClick={() => (open ? closeMenu() : openMenu())}
      >
        <span className="ui-dropdown-value">{selectedLabel}</span>
        <ChevronIcon />
      </button>

      {open && (
        <ul ref={listRef} id={listId} className="ui-dropdown-menu" role="listbox" aria-label={ariaLabel}>
          {options.map((option, index) => (
            <li
              key={option.value}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === selectedIndex}
              data-active={index === activeIndex ? "true" : "false"}
              className="ui-dropdown-option"
              onPointerEnter={() => setActiveIndex(index)}
              onClick={() => commit(index)}
            >
              <span className="ui-dropdown-option-label">{option.label}</span>
              <CheckIcon />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default Dropdown;
