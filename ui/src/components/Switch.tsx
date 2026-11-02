import type { ReactNode } from "react";
import * as RadixSwitch from "@radix-ui/react-switch";
import clsx from "clsx";

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  id?: string;
  ariaLabel?: string;
  className?: string;
}

/** Radix switch with an Apple-style label row. */
export default function Switch({ checked, onChange, label, description, disabled, id, ariaLabel, className }: SwitchProps) {
  const control = (
    <RadixSwitch.Root
      id={id}
      className="switch-root"
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      aria-label={ariaLabel ?? (typeof label === "string" ? label : undefined)}
    >
      <RadixSwitch.Thumb className="switch-thumb" />
    </RadixSwitch.Root>
  );
  if (label == null && description == null) return <div className={className}>{control}</div>;
  return (
    <div className={clsx("switch-row", className)}>
      <label className="switch-text" htmlFor={id} style={{ cursor: disabled ? "default" : "pointer" }}>
        {label != null ? <div className="switch-title">{label}</div> : null}
        {description != null ? <div className="switch-desc">{description}</div> : null}
      </label>
      {control}
    </div>
  );
}
