import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "plain";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: LucideIcon;
  iconRight?: LucideIcon;
  block?: boolean;
  /** Internal "/" links render a react-router Link; other URLs render an anchor. */
  href?: string;
}

function ButtonContent({ loading, icon: Icon, iconRight: IconRight, children }: Pick<ButtonProps, "loading" | "icon" | "iconRight" | "children">) {
  return (
    <>
      {loading ? <Loader2 size={16} className="spin" aria-hidden="true" /> : Icon ? <Icon size={16} aria-hidden="true" /> : null}
      {children != null ? <span className="btn-label">{children as ReactNode}</span> : null}
      {IconRight ? <IconRight size={16} aria-hidden="true" /> : null}
    </>
  );
}

/** Single button primitive used by every page (DESIGN-SPEC §4.1). */
const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, icon, iconRight, block, className, children, disabled, type = "button", href, ...rest },
  ref,
) {
  const classes = clsx("btn", `btn-${variant}`, size !== "md" && `btn-${size}`, block && "btn-block", loading && "btn-loading", className);
  const content = <ButtonContent loading={loading} icon={icon} iconRight={iconRight}>{children}</ButtonContent>;
  if (href) {
    if (href.startsWith("/")) {
      return <Link to={href} className={classes}>{content}</Link>;
    }
    return <a href={href} className={classes} target="_blank" rel="noreferrer">{content}</a>;
  }
  return (
    <button ref={ref} type={type} className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {content}
    </button>
  );
});

Button.displayName = "Button";
export { Button };
export default Button;
