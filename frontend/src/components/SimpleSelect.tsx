import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export type SimpleSelectOption = { value: string; label: string };

// The app's styled dropdown for a plain list of choices, so screens do not fall back to the
// browser's native <select>, which looks different on every system.
export function SimpleSelect({
  value,
  options,
  onChange,
  label,
  placeholder,
  className,
  tall = false,
}: {
  tall?: boolean;
  value: string;
  options: SimpleSelectOption[];
  onChange: (value: string) => void;
  label: string;
  placeholder?: string;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        aria-label={label}
        size="sm"
        className={cn(
          "bg-card",
          // Taller to sit level with the other controls in a toolbar.
          tall && "data-[size=sm]:h-10",
          className,
        )}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
