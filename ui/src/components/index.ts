/**
 * Component library barrel — docs/DESIGN-SPEC.md v2 §4.
 * Prefer named imports: `import { Button, Card, PageHeader } from "../components"`.
 */

/* ---------- v2 primitives (§4.1) ---------- */
export { default as Button } from "./Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button";
export { default as Field } from "./Field";
export type { FieldProps } from "./Field";
export { default as Input } from "./Input";
export type { InputProps } from "./Input";
export { default as Textarea } from "./Textarea";
export type { TextareaProps } from "./Textarea";
export { default as Select } from "./Select";
export type { SelectProps, SelectOption } from "./Select";
export { default as Switch } from "./Switch";
export type { SwitchProps } from "./Switch";
export { default as Segmented } from "./Segmented";
export type { SegmentedProps, SegmentedOption, SegmentedItem } from "./Segmented";
export { default as Tabs } from "./Tabs";
export type { TabsProps, TabItem } from "./Tabs";
export { default as PageHeader } from "./PageHeader";
export type { PageHeaderProps, PageHeaderBreadcrumb } from "./PageHeader";
export { default as Callout } from "./Callout";
export type { CalloutProps, CalloutTone } from "./Callout";
export { default as List, ListRow, ListSep } from "./List";
export type { ListProps, ListRowProps } from "./List";
export { default as ProgressBar } from "./ProgressBar";
export type { ProgressBarProps, ProgressTone } from "./ProgressBar";
export { default as Dialog } from "./Dialog";
export type { DialogProps, DialogSize } from "./Dialog";
export { default as Sheet } from "./Sheet";
export type { SheetProps, SheetSide } from "./Sheet";
export { default as Menu } from "./Menu";
export type { MenuProps, MenuItem } from "./Menu";
export { default as Tooltip } from "./Tooltip";
export type { TooltipProps } from "./Tooltip";
export { default as Popover } from "./Popover";
export type { PopoverProps } from "./Popover";
export { Toaster } from "./Toaster";
export { default as Toasts } from "./Toasts";

/* ---------- v2 business components (§4.2) ---------- */
export { default as Panel } from "./Panel";
export type { PanelProps, PanelTone } from "./Panel";
export { default as Card } from "./Panel";
export { default as StatTile } from "./StatTile";
export type { StatTileProps } from "./StatTile";
export { default as SectionHeader } from "./SectionHeader";
export type { SectionHeaderProps } from "./SectionHeader";
export { default as Toolbar } from "./Toolbar";
export type { ToolbarProps } from "./Toolbar";
export { default as Badge, Tag } from "./Badge";
export type { BadgeProps, TagProps, Tone } from "./Badge";
export { default as DataTable } from "./DataTable";
export type { DataTableProps, DataTableColumn } from "./DataTable";
export { default as Sparkline } from "./Sparkline";
export type { SparklineProps } from "./Sparkline";
export { default as ChartCard } from "./ChartCard";
export type { ChartCardProps } from "./ChartCard";
export { default as EmptyState } from "./EmptyState";
export type { EmptyStateProps } from "./EmptyState";
export { default as Skeleton } from "./Skeleton";
export type { SkeletonProps } from "./Skeleton";
export { default as StepList } from "./StepList";
export type { StepListProps, StepListItem } from "./StepList";
export { default as MetricPill } from "./MetricPill";
export type { MetricPillProps } from "./MetricPill";
export { default as QuoteRow } from "./QuoteRow";
export type { QuoteRowProps } from "./QuoteRow";
export { default as CommandPalette } from "./CommandPalette";
export type { CommandPaletteProps, CommandPaletteItem } from "./CommandPalette";
export { default as Chart } from "./Chart";
export type { ChartProps, ChartSeries, ChartSeriesKind, ChartPoint, ChartCandle } from "./Chart";
export { default as KLineChart } from "./KLineChart";

/* ---------- shell + compatibility (default exports preserved) ---------- */
export { default as AppBar } from "./AppBar";
export { default as Rail, MobileTabBar } from "./Rail";
export { default as StatusBar } from "./StatusBar";
export { default as Onboarding } from "./Onboarding";
export { default as ErrorBoundary } from "./ErrorBoundary";
export { default as GlobalSearch } from "./GlobalSearch";
export { MetricCard } from "./MetricCard";
export { default as ParamForm, defaultsFromSchema } from "./ParamForm";
export { default as PaperPortfolioPanel } from "./PaperPortfolioPanel";
export { default as RobustnessPanel } from "./RobustnessPanel";
export { default as StatePanel } from "./StatePanel";
export { default as VirtualTable } from "./VirtualTable";

