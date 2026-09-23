// Same icon method as spoorkaart: themed SVG components, currentColor fills,
// and a hover class. Colour comes from --icon-color on .app-controls.

const ICON_COLORS = {
  color2: "#FEC226",
};

const THEMED_ICON_COLOR = `var(--icon-color, ${ICON_COLORS.color2})`;

const ICON_COLOR_MAP: Record<string, string> = {
  SettingsIcon: THEMED_ICON_COLOR,
  ColorOnIcon: THEMED_ICON_COLOR,
  ThinTracksIcon: THEMED_ICON_COLOR,
  NormalTracksIcon: THEMED_ICON_COLOR,
  ThinStationsIcon: THEMED_ICON_COLOR,
  MediumStationsIcon: THEMED_ICON_COLOR,
  NormalStationsIcon: THEMED_ICON_COLOR,
  DitherOnIcon: THEMED_ICON_COLOR,
  DitherOffIcon: THEMED_ICON_COLOR,
};

const DEFAULT_ICON_SIZE = 20;

function getIconHoverClass(): string {
  return "icon-hover-effect";
}

interface IconProps {
  className?: string;
  size?: number;
  onClick?: () => void;
}

export function SettingsIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.SettingsIcon }}
    >
      <path
        opacity="0.4"
        d="M15.9391 7.44101L14.8771 7.27802C14.7531 6.85402 14.5851 6.447 14.3721 6.06L15.0081 5.19299C15.3761 4.69199 15.3241 4.00801 14.8841 3.57001L14.4281 3.11401C13.9901 2.67501 13.3071 2.62299 12.8041 2.98999L11.9371 3.62701C11.5501 3.41401 11.1431 3.24601 10.7201 3.12201L10.5561 2.05899C10.4611 1.44499 9.94208 0.998993 9.32108 0.998993H8.67609C8.05509 0.998993 7.53509 1.445 7.44109 2.06L7.27808 3.12201C6.85408 3.24601 6.44709 3.41401 6.06009 3.62701L5.19308 2.991C4.69108 2.624 4.00808 2.676 3.57008 3.116L3.11409 3.57199C2.67509 4.01099 2.62309 4.69401 2.99009 5.19601L3.62709 6.06299C3.41509 6.44999 3.24609 6.857 3.12209 7.28L2.05909 7.444C1.44509 7.539 0.999084 8.05799 0.999084 8.67899V9.32401C0.999084 9.94501 1.44509 10.465 2.06009 10.559L3.12209 10.722C3.24609 11.146 3.41409 11.553 3.62709 11.94L2.99109 12.807C2.62409 13.308 2.67609 13.991 3.11609 14.43L3.57209 14.886C4.01109 15.326 4.69508 15.378 5.19608 15.01L6.06308 14.373C6.45008 14.585 6.85709 14.754 7.28009 14.878L7.44408 15.941C7.53908 16.555 8.05808 17.001 8.67908 17.001H9.32409C9.94509 17.001 10.4651 16.555 10.5591 15.94L10.7221 14.878C11.1461 14.754 11.5531 14.586 11.9401 14.373L12.8071 15.009C13.3081 15.377 13.9911 15.324 14.4301 14.885L14.8861 14.429C15.3251 13.99 15.3771 13.307 15.0101 12.805L14.3731 11.938C14.5861 11.551 14.7541 11.144 14.8781 10.721L15.9411 10.557C16.5551 10.462 17.0011 9.94299 17.0011 9.32199V8.677C17.0011 8.056 16.5551 7.53599 15.9411 7.44199L15.9391 7.44101Z"
        fill="currentColor"
      ></path>
      <path
        d="M9.00009 11.5C10.3808 11.5 11.5001 10.3807 11.5001 9C11.5001 7.61929 10.3808 6.5 9.00009 6.5C7.61938 6.5 6.50009 7.61929 6.50009 9C6.50009 10.3807 7.61938 11.5 9.00009 11.5Z"
        fill="currentColor"
      ></path>
    </svg>
  );
}

export function ColorOnIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.ColorOnIcon }}
    >
      <path
        d="M4.5 16L14.25 16C15.2162 16 16 15.2162 16 14.25V12.75C16 11.7838 15.2162 11 14.25 11L10.5355 11L6.41421 15.1213L4.5 16Z"
        fill="currentColor"
        fillOpacity="0.2"
      ></path>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M9.77291 4.69149L2.87861 11.5858C1.9023 12.5621 1.9023 14.145 2.87861 15.1213C3.85492 16.0976 5.43784 16.0976 6.41415 15.1213L13.3084 8.22703C13.9917 7.54381 13.9917 6.43537 13.3084 5.75215L12.2478 4.69149C11.5646 4.00828 10.4561 4.00828 9.77291 4.69149ZM4.49999 14.5C5.05227 14.5 5.49999 14.0523 5.49999 13.5C5.49999 12.9477 5.05227 12.5 4.49999 12.5C3.9477 12.5 3.49999 12.9477 3.49999 13.5C3.49999 14.0523 3.9477 14.5 4.49999 14.5Z"
        fill="currentColor"
        fillOpacity="0.4"
      ></path>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M2.00001 3.75L2 13.5C2 14.8807 3.11929 16 4.5 16C5.88072 16 7.00001 14.8807 7.00001 13.5V3.75C7.00001 2.78379 6.21622 2 5.25001 2H3.75001C2.78379 2 2.00001 2.78379 2.00001 3.75ZM5.5 13.5C5.5 14.052 5.052 14.5 4.5 14.5C3.948 14.5 3.5 14.052 3.5 13.5C3.5 12.948 3.948 12.5 4.5 12.5C5.052 12.5 5.5 12.948 5.5 13.5Z"
        fill="currentColor"
      ></path>
    </svg>
  );
}

export function ThinTracksIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.ThinTracksIcon }}
    >
      <rect x="2" y="8.25" width="14" height="1.5" rx="0.75" fill="currentColor" />
    </svg>
  );
}

export function NormalTracksIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.NormalTracksIcon }}
    >
      <rect x="2" y="6.5" width="14" height="5" rx="1.5" fill="currentColor" />
    </svg>
  );
}

export function ThinStationsIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.ThinStationsIcon }}
    >
      <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.25" />
    </svg>
  );
}

/** Same circle-stroke stations icon, weighted between the thin and normal faces. */
export function MediumStationsIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.MediumStationsIcon }}
    >
      <circle cx="9" cy="9" r="5.25" fill="none" stroke="currentColor" strokeWidth="2.25" />
    </svg>
  );
}

export function NormalStationsIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.NormalStationsIcon }}
    >
      <circle cx="9" cy="9" r="5" fill="none" stroke="currentColor" strokeWidth="3.5" />
    </svg>
  );
}

const DITHER_DOTS_SOLID: ReadonlyArray<readonly [number, number]> = [
  [3, 3],
  [15, 3],
  [9, 9],
  [3, 15],
  [15, 15],
];

const DITHER_DOTS_FADED: ReadonlyArray<readonly [number, number]> = [
  [9, 3],
  [3, 9],
  [15, 9],
  [9, 15],
];

export function DitherOnIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.DitherOnIcon }}
    >
      {DITHER_DOTS_FADED.map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="1" fill="currentColor" opacity="0.4" />
      ))}
      {DITHER_DOTS_SOLID.map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="1" fill="currentColor" />
      ))}
    </svg>
  );
}

export function DitherOffIcon({ className = "", size = DEFAULT_ICON_SIZE, onClick }: IconProps) {
  const hoverClass = getIconHoverClass();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className={`${className} ${hoverClass}`}
      onClick={onClick}
      style={{ color: ICON_COLOR_MAP.DitherOffIcon }}
    >
      {[...DITHER_DOTS_FADED, ...DITHER_DOTS_SOLID].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="1" fill="currentColor" opacity="0.4" />
      ))}
    </svg>
  );
}
