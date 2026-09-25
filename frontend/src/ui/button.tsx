import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

type ButtonVariant = "default" | "primary" | "quiet";
type ButtonSize = "sm" | "md" | "lg";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
  trailingIcon?: ReactNode;
  busy?: boolean;
};

const VARIANTS: Record<ButtonVariant, string> = {
  default:
    "border-line-control bg-surface-raised text-text-primary hover:border-line-strong hover:bg-surface-sunken",
  primary: "border-primary-fill bg-primary-fill text-primary-text hover:opacity-90",
  quiet:
    "border-transparent bg-transparent text-text-secondary underline underline-offset-2 hover:border-line-control hover:text-text-primary",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-6 gap-1.5 px-2 text-[12px]",
  md: "h-7 gap-2 px-2.5 text-[13px]",
  lg: "h-9 gap-2 px-3.5 text-[13px]",
};

export const BUTTON_BASE =
  "relative inline-flex shrink-0 items-center justify-center rounded-[var(--radius-ctl)] border font-medium whitespace-nowrap transition-[background-color,border-color,opacity] duration-[var(--t-2)] ease-[var(--e-std)] active:translate-y-px disabled:pointer-events-none disabled:border-dashed disabled:border-line-control disabled:bg-transparent disabled:text-text-tertiary disabled:no-underline";

export function buttonClasses(
  variant: ButtonVariant = "default",
  size: ButtonSize = "md",
  className?: string,
): string {
  return cn(BUTTON_BASE, VARIANTS[variant], SIZES[size], className);
}

export function Button({
  variant = "default",
  size = "md",
  icon,
  trailingIcon,
  busy,
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      aria-busy={busy || undefined}
      className={buttonClasses(variant, size, className)}
      {...props}
    >
      {icon}
      {children}
      {trailingIcon}
      {busy ? (
        <span
          aria-hidden
          className="absolute inset-x-0 -bottom-px h-0.5 animate-pulse bg-text-secondary"
        />
      ) : null}
    </button>
  );
}

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  shortcut?: string;
  pressed?: boolean;
  size?: "sm" | "md" | "lg";
};

const ICON_SIZES = { sm: "size-6", md: "size-8", lg: "size-10" } as const;

export function IconButton({
  label,
  shortcut,
  pressed,
  size = "md",
  className,
  children,
  type = "button",
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={shortcut ? `${label} · ${shortcut}` : label}
      aria-pressed={pressed}
      className={cn(
        "grid shrink-0 place-items-center rounded-[var(--radius-ctl)] border border-line-control bg-surface-panel text-text-secondary transition-colors duration-[var(--t-2)] hover:bg-surface-raised hover:text-text-primary",
        "disabled:pointer-events-none disabled:border-dashed disabled:bg-transparent disabled:text-text-disabled",
        pressed &&
          "border-primary-fill bg-primary-fill text-primary-text hover:bg-primary-fill hover:text-primary-text",
        ICON_SIZES[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
