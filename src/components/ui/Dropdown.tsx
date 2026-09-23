"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

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

const MENU_GAP = 6;
const MENU_MARGIN = 8;

type MenuBox = {
  top: number;
  left: number;
  width: number;
  placement: "down" | "up";
};

/** Fixed coordinates so the menu is not inside the settings scroller. */
function placeMenu(trigger: DOMRect, menuWidth: number, menuHeight: number, align: "start" | "end"): MenuBox {
  const overflowsBottom = trigger.bottom + MENU_GAP + menuHeight > window.innerHeight - MENU_MARGIN;
  const placement = overflowsBottom ? "up" : "down";
  let top = placement === "up" ? trigger.top - MENU_GAP - menuHeight : trigger.bottom + MENU_GAP;
  const maxTop = window.innerHeight - MENU_MARGIN - menuHeight;
  top = Math.min(Math.max(MENU_MARGIN, top), Math.max(MENU_MARGIN, maxTop));
  let left = align === "end" ? trigger.right - menuWidth : trigger.left;
  const maxLeft = window.innerWidth - MENU_MARGIN - menuWidth;
  left = Math.min(Math.max(MENU_MARGIN, left), Math.max(MENU_MARGIN, maxLeft));
  return { top, left, width: menuWidth, placement };
}

function menuStyle(box: MenuBox | null): CSSProperties {
  if (!box) {
    return { top: 0, left: 0, visibility: "hidden", pointerEvents: "none" };
  }
  return { top: box.top, left: box.left, width: box.width, visibility: "visible" };
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
  const [menuBox, setMenuBox] = useState<MenuBox | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const selectedIndex = options.findIndex((option) => option.value === value);
  const selectedLabel = selectedIndex >= 0 ? options[selectedIndex].label : (fallbackLabel ?? "");

  const closeMenu = useCallback(() => {
    setOpen(false);
    setActiveIndex(-1);
    setMenuBox(null);
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
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || listRef.current?.contains(target)) return;
      closeMenu();
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open, closeMenu]);

  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const trigger = triggerRef.current;
      const list = listRef.current;
      if (!trigger || !list) return;
      const rect = trigger.getBoundingClientRect();
      const locked = list.style.width;
      list.style.width = "max-content";
      const contentWidth = list.offsetWidth;
      list.style.width = locked;
      const width = Math.max(rect.width, contentWidth);
      list.style.width = `${width}px`;
      const next = placeMenu(rect, width, list.offsetHeight, align);
      list.style.width = locked;
      setMenuBox((current) =>
        current &&
        current.top === next.top &&
        current.left === next.left &&
        current.width === next.width &&
        current.placement === next.placement
          ? current
          : next,
      );
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, align, options]);

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    const list = listRef.current;
    const item = list?.children[activeIndex] as HTMLElement | undefined;
    if (!list || !item) return;
    const itemTop = item.offsetTop;
    const itemBottom = itemTop + item.offsetHeight;
    if (itemTop < list.scrollTop) list.scrollTop = itemTop;
    else if (itemBottom > list.scrollTop + list.clientHeight) list.scrollTop = itemBottom - list.clientHeight;
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

      {open &&
        createPortal(
          <ul
            ref={listRef}
            id={listId}
            className="ui-dropdown-menu"
            role="listbox"
            aria-label={ariaLabel}
            data-placement={menuBox?.placement ?? "down"}
            style={menuStyle(menuBox)}
          >
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
          </ul>,
          document.body,
        )}
    </div>
  );
}

export default Dropdown;
