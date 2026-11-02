import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  invalid?: boolean;
  size?: "sm" | "md" | "lg";
  icon?: LucideIcon;
  trailing?: ReactNode;
}

const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid, size = "md", icon: Icon, trailing, className, ...rest },
  ref,
) {
  const input = (
    <input
      ref={ref}
      className={clsx("input", size !== "md" && `input-${size}`, className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
  if (!Icon && !trailing) return input;
  return (
    <div className="input-wrap">
      {Icon ? <span className="input-wrap-icon"><Icon size={16} aria-hidden="true" /></span> : null}
      {input}
      {trailing ? <span className="input-wrap-trailing">{trailing}</span> : null}
    </div>
  );
});

Input.displayName = "Input";
export default Input;
