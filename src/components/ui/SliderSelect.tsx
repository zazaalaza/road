"use client";

import { useCallback, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

export type SliderOption<T extends string | number> = {
  value: T;
  label: string;
};

type SliderSelectProps<T extends string | number> = {
  value: T;
  options: readonly SliderOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
};

function SliderSelect<T extends string | number>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
}: SliderSelectProps<T>) {
  const railRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  const lastIndex = options.length - 1;
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const selected = options[selectedIndex];
  const position = lastIndex > 0 ? (selectedIndex / lastIndex) * 100 : 0;

  const commitIndex = useCallback(
    (index: number) => {
      const clamped = Math.min(lastIndex, Math.max(0, index));
      const option = options[clamped];
      if (option && option.value !== value) onChange(option.value);
    },
    [lastIndex, onChange, options, value],
  );

  const commitFromClientX = useCallback(
    (clientX: number) => {
      const rail = railRef.current;
      if (!rail) return;
      const bounds = rail.getBoundingClientRect();
      if (bounds.width === 0) return;
      const ratio = (clientX - bounds.left) / bounds.width;
      commitIndex(Math.round(ratio * lastIndex));
    },
    [commitIndex, lastIndex],
  );

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    commitFromClientX(event.clientX);
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    commitFromClientX(event.clientX);
  };

  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragging(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowLeft":
      case "ArrowDown":
        event.preventDefault();
        commitIndex(selectedIndex - 1);
        return;
      case "ArrowRight":
      case "ArrowUp":
        event.preventDefault();
        commitIndex(selectedIndex + 1);
        return;
      case "Home":
        event.preventDefault();
        commitIndex(0);
        return;
      case "End":
        event.preventDefault();
        commitIndex(lastIndex);
        return;
      default:
    }
  };

  return (
    <div
      className={className ? `ui-slider ${className}` : "ui-slider"}
      data-dragging={dragging ? "true" : "false"}
      role="slider"
      tabIndex={0}
      aria-label={ariaLabel}
      aria-valuemin={0}
      aria-valuemax={lastIndex}
      aria-valuenow={selectedIndex}
      aria-valuetext={selected?.label}
      title={selected?.label}
      onKeyDown={handleKeyDown}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      <div className="ui-slider-rail" ref={railRef}>
        <div className="ui-slider-fill" style={{ width: `${position}%` }} />
        {options.map((option, index) => (
          <span
            key={option.value}
            className="ui-slider-tick"
            data-passed={index <= selectedIndex ? "true" : "false"}
            style={{ left: `${lastIndex > 0 ? (index / lastIndex) * 100 : 0}%` }}
          />
        ))}
        <span className="ui-slider-thumb" style={{ left: `${position}%` }} />
      </div>
    </div>
  );
}

export default SliderSelect;
