import { forwardRef, type SelectHTMLAttributes } from "react";
import clsx from "clsx";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  options?: SelectOption[];
  placeholder?: string;
  invalid?: boolean;
  size?: "sm" | "md" | "lg";
}

/** Styled native select: keeps native form + Playwright selectOption behaviour. */
const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { options, placeholder, invalid, size = "md", className, children, ...rest },
  ref,
) {
  return (
    <select
      ref={ref}
      className={clsx("select", size !== "md" && `input-${size}`, className)}
      aria-invalid={invalid || undefined}
      {...rest}
    >
      {placeholder ? <option value="" disabled>{placeholder}</option> : null}
      {options
        ? options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>
          ))
        : children}
    </select>
  );
});

Select.displayName = "Select";
export default Select;
