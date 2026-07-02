import { cn } from "@/lib/utils";

const toneClasses = {
  neutral: "border-line bg-white text-slate-700",
  teal: "border-teal/25 bg-teal/10 text-teal",
  amber: "border-amber/30 bg-amber/10 text-amber",
  rose: "border-rose/25 bg-rose/10 text-rose",
  cobalt: "border-cobalt/25 bg-cobalt/10 text-cobalt"
};

export function Badge({
  children,
  tone = "neutral",
  className
}: {
  children: React.ReactNode;
  tone?: keyof typeof toneClasses;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium", toneClasses[tone], className)}>
      {children}
    </span>
  );
}
