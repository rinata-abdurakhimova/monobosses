import type { CSSProperties } from "react";

export type IconName =
  | "plus"
  | "arrow"
  | "book"
  | "layers"
  | "check"
  | "close"
  | "chevron"
  | "flask"
  | "clock"
  | "warning"
  | "file"
  | "spark";
const paths: Record<IconName, string> = {
  plus: "M12 5v14M5 12h14",
  arrow: "M5 12h14M13 6l6 6-6 6",
  book: "M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H4zM13 7a3 3 0 0 1 3-3h4v14h-3a4 4 0 0 0-4 3",
  layers: "m12 3 9 5-9 5-9-5 9-5M3 12l9 5 9-5M3 16l9 5 9-5",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12M18 6 6 18",
  chevron: "m6 9 6 6 6-6",
  flask: "M9 3h6M10 3v6L4 19a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M8 14h8",
  clock: "M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  warning: "m12 3 10 18H2L12 3M12 9v5M12 17v.1",
  file: "M14 3H5v18h14V8l-5-5M14 3v5h5M8 12h8M8 16h6",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3",
};
export function Icon({
  name,
  size = 20,
  style,
}: {
  name: IconName;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      <path d={paths[name]} />
    </svg>
  );
}
