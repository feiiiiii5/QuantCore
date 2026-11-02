/**
 * Component library barrel — docs/DESIGN-SPEC.md §5.
 * New components are named exports; legacy components keep their default export and are
 * also re-exported here so pages can `import { Panel, Chart, VirtualTable } from "../components"`.
 */

export { default as Panel } from "./Panel";
export type { PanelProps, PanelTone } from "./Panel";
export { default as StatTile } from "./StatTile";
export type { StatTileProps } from "./StatTile";
export { default as SectionHeader } from "./SectionHeader";
export type { SectionHeaderProps } from "./SectionHeader";
export { default as Toolbar } from "./Toolbar";
export type { ToolbarProps } from "./Toolbar";
export { default as Segmented } from "./Segmented";
export type { SegmentedProps, SegmentedOption } from "./Segmented";
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
export { default as Tabs } from "./Tabs";
export type { TabsProps, TabItem } from "./Tabs";
export { default as MetricPill } from "./MetricPill";
export type { MetricPillProps } from "./MetricPill";
export { default as QuoteRow } from "./QuoteRow";
export type { QuoteRowProps } from "./QuoteRow";
export { default as CommandPalette } from "./CommandPalette";
export type { CommandPaletteProps, CommandPaletteItem } from "./CommandPalette";

/* legacy components kept for compatibility (default exports preserved) */
export { default as Chart } from "./Chart";
export { default as ErrorBoundary } from "./ErrorBoundary";
export { default as GlobalSearch } from "./GlobalSearch";
export { default as KLineChart } from "./KLineChart";
export { MetricCard } from "./MetricCard";
export { default as Onboarding } from "./Onboarding";
export { default as ParamForm, defaultsFromSchema } from "./ParamForm";
export { default as PaperPortfolioPanel } from "./PaperPortfolioPanel";
export { default as RobustnessPanel } from "./RobustnessPanel";
export { default as StatePanel } from "./StatePanel";
export { default as StatusBar } from "./StatusBar";
export { default as Toasts } from "./Toasts";
export { default as VirtualTable } from "./VirtualTable";
